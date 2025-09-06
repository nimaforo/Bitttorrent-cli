# client.py: Core logic for leeching and seeding.

import socket
import threading
import time
import logging
from tracker import Tracker
from peer import Peer
from piece_manager import PieceManager
from file_manager import FileManager
from torrent import Torrent
from utils import generate_peer_id

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class Client:
    def __init__(self, torrent_path, output_dir, seed=False):
        """Initialize the BitTorrent client."""
        self.torrent = Torrent(torrent_path)
        self.output_dir = output_dir
        self.peer_id = generate_peer_id()
        self.port = 6881
        self.seed = seed
        
        # Initialize managers
        self.file_manager = FileManager(self.torrent, output_dir)
        self.piece_manager = PieceManager(self.torrent, self.file_manager)
        self.tracker = Tracker(self.torrent)
        self.tracker.peer_id = self.peer_id
        self.tracker.port = self.port
        
        # Peer management
        self.active_peers = {}  # ip:port -> Peer
        self.running = False
        self.download_complete = False
        
        # Stats
        self.uploaded = 0
        self.downloaded = 0
        self.start_time = 0
        
    def start(self):
        """Start the client."""
        try:
            self.running = True
            self.start_time = time.time()
            
            print(f"\n=== Starting BitTorrent {'Seeding' if self.seed else 'Download'} ===")
            print(f"Name: {self.torrent.name}")
            print(f"Size: {self.format_size(self.torrent.total_length)}")
            print(f"Pieces: {self.torrent.num_pieces} ({self.format_size(self.torrent.piece_length)} each)")
            print(f"Tracker: {self.torrent.announce}")
            print()
            
            if self.seed:
                self._start_seeding()
            else:
                self._start_downloading()
                
        except KeyboardInterrupt:
            print("\nStopping client...")
        except Exception as e:
            logging.error(f"Client error: {str(e)}")
        finally:
            self.stop()
            
    def _start_downloading(self):
        """Start download mode."""
        print("=== Starting Download ===")
        
        # Get peer list from tracker
        print(f"\nConnecting to tracker: {self.torrent.announce}")
        peers = self.tracker.get_peers()
        
        if not peers:
            print("Failed to get peers from tracker. Trying alternative methods:")
            print("1. Using DHT (Distributed Hash Table) - Not implemented")
            print("2. Using Peer Exchange (PEX) - Not implemented") 
            print("3. Trying common tracker alternatives...")
            
            # Try some common public trackers as fallback
            fallback_trackers = [
                "http://tracker.openbittorrent.com:80/announce",
                "udp://tracker.openbittorrent.com:80/announce",
                "http://tracker.publicbt.com:80/announce"
            ]
            
            for tracker_url in fallback_trackers:
                try:
                    print(f"Trying fallback tracker: {tracker_url}")
                    # Create a new tracker instance for the fallback
                    fallback_tracker = Tracker(self.torrent)
                    fallback_tracker.torrent.announce = tracker_url
                    peers = fallback_tracker.get_peers()
                    if peers:
                        print(f"Found {len(peers)} peers from fallback tracker")
                        break
                except Exception as e:
                    print(f"Fallback tracker failed: {e}")
                    continue
        
        if not peers:
            print("\n❌ No peers found from any tracker. Cannot start download.")
            print("\n🔍 Diagnosis:")
            
            # Check what type of trackers this torrent uses
            tracker_types = []
            if self.torrent.announce.startswith('http'):
                tracker_types.append("HTTP")
            elif self.torrent.announce.startswith('udp'):
                tracker_types.append("UDP") 
            elif self.torrent.announce.startswith('ws'):
                tracker_types.append("WebSocket")
                
            if hasattr(self.torrent, 'announce_list'):
                for tracker_group in self.torrent.announce_list:
                    for tracker in tracker_group:
                        if tracker.startswith('udp') and "UDP" not in tracker_types:
                            tracker_types.append("UDP")
                        elif tracker.startswith('ws') and "WebSocket" not in tracker_types:
                            tracker_types.append("WebSocket")
            
            print(f"   Torrent uses: {', '.join(tracker_types)} trackers")
            
            if "UDP" in tracker_types:
                print("   ⚠️  This torrent primarily uses UDP trackers (limited support)")
            if "WebSocket" in tracker_types:
                print("   ⚠️  This torrent uses WebSocket trackers (not supported)")
                
            print("\n💡 Possible solutions:")
            print("1. Try a torrent that uses HTTP trackers")
            print("2. Check your internet connection") 
            print("3. Try a more popular/recent torrent with active seeders")
            print("4. Use a VPN if your ISP blocks BitTorrent")
            print("5. Try a different torrent client for UDP tracker support")
            
            print("\n📋 For testing your client, try:")
            print("   python main.py --torrent test.torrent --output downloads/")
            print("   (After starting: python test_tracker.py and python start_seeder.py)")
            return
            
        print(f"Found {len(peers)} peers")
        
        # Start peer connections
        successful_peers = 0
        max_peers = min(10, len(peers))  # Limit concurrent connections
        
        for i, (ip, port) in enumerate(peers[:max_peers]):
            if (ip, port) not in self.active_peers:
                try:
                    print(f"\nConnecting to peer {ip}:{port}")
                    peer = Peer(ip, port, self.torrent, self.peer_id, self.piece_manager)
                    if peer.connect():
                        self.active_peers[(ip, port)] = peer
                        threading.Thread(target=self._handle_peer, args=(peer,), daemon=True).start()
                        successful_peers += 1
                        print(f"Successfully connected to peer {ip}:{port}")
                    else:
                        print(f"Failed to connect to peer {ip}:{port}")
                except Exception as e:
                    print(f"Error connecting to peer {ip}:{port}: {str(e)}")
                    continue
        
        if successful_peers == 0:
            print("\nNo peers connected successfully.")
            print("This could be due to:")
            print("1. Firewall blocking connections")
            print("2. All peers are offline")
            print("3. Network connectivity issues")
            print("4. Tracker provided invalid peer information")
            return
        
        print(f"\nSuccessfully connected to {successful_peers} peers")
        print("Download in progress...")
        
        # Main download loop
        while self.running and not self.download_complete:
            self._manage_downloads()
            
            # Periodically try to get more peers
            if len(self.active_peers) < 3:
                try:
                    new_peers = self.tracker.get_peers()
                    for ip, port in new_peers[:5]:
                        if (ip, port) not in self.active_peers:
                            try:
                                peer = Peer(ip, port, self.torrent, self.peer_id, self.piece_manager)
                                if peer.connect():
                                    self.active_peers[(ip, port)] = peer
                                    threading.Thread(target=self._handle_peer, args=(peer,), daemon=True).start()
                                    print(f"Added new peer {ip}:{port}")
                            except Exception:
                                continue
                except Exception:
                    pass
            
            time.sleep(2)
            
    def _start_seeding(self):
        """Start seeding mode."""
        print("=== Starting Seeding ===")
        
        # For seeding, assume we have all pieces
        for i in range(self.torrent.num_pieces):
            self.piece_manager.have_pieces.add(i)
        
        # Start listening for incoming connections
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server.bind(('', self.port))
            server.listen(5)
            print(f"Listening on port {self.port} for incoming connections...")
            
            # Register with tracker
            self.tracker.get_peers()
            
            server.settimeout(1)
            while self.running:
                try:
                    conn, addr = server.accept()
                    print(f"Accepted connection from {addr[0]}:{addr[1]}")
                    peer = Peer(addr[0], addr[1], self.torrent, self.peer_id, self.piece_manager, is_seeding=True)
                    threading.Thread(target=peer.handle_incoming, args=(conn,), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error accepting connection: {e}")
        finally:
            server.close()
            
    def stop(self):
        """Stop the client and clean up."""
        self.running = False
        for peer in list(self.active_peers.values()):
            try:
                peer.close()
            except:
                pass
        self.active_peers.clear()
        self.file_manager.close()
        
    def _handle_peer(self, peer):
        """Handle communication with a peer."""
        try:
            while self.running and not self.download_complete:
                peer.handle_messages()
        except Exception as e:
            print(f"Peer {peer.ip}:{peer.port} error: {str(e)}")
        finally:
            try:
                peer.close()
            except:
                pass
            if (peer.ip, peer.port) in self.active_peers:
                del self.active_peers[(peer.ip, peer.port)]
                
    def _manage_downloads(self):
        """Manage piece requests and track progress."""
        total_pieces = self.torrent.num_pieces
        have_pieces = len(self.piece_manager.have_pieces)
        progress = (have_pieces / total_pieces) * 100 if total_pieces > 0 else 0
        
        # Calculate speed
        current_time = time.time()
        elapsed = current_time - self.start_time
        download_speed = self.downloaded / elapsed if elapsed > 0 else 0
        
        # Show progress every few pieces to avoid spam
        if have_pieces % 10 == 0 or have_pieces == total_pieces or elapsed % 10 < 1:
            print(f"Progress: {progress:.2f}% ({have_pieces}/{total_pieces} pieces) - "
                  f"Speed: {download_speed/1024:.2f} KB/s - "
                  f"Active peers: {len(self.active_peers)}")
        
        if have_pieces == total_pieces:
            print("Download complete!")
            self.download_complete = True

    @staticmethod
    def format_size(size):
        """Format size in bytes to human readable string."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} TB"
