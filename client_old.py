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
        self.complete = False
        
        # Stats
        self.uploaded = 0
        self.downloaded = 0
        self.start_time = 0
        
        # Start progress display thread
        self.progress_thread = threading.Thread(target=self.show_progress)
        self.progress_thread.daemon = True
        self.progress_thread.start()
        
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
                    self.tracker.torrent.announce = tracker_url
                    peers = self.tracker.get_peers()
                    if peers:
                        print(f"Found {len(peers)} peers from fallback tracker")
                        break
                except Exception as e:
                    print(f"Fallback tracker failed: {e}")
                    continue
        
        if not peers:
            print("\nNo peers found from any tracker. Cannot start download.")
            print("\nPossible solutions:")
            print("1. Check your internet connection")
            print("2. Try a different torrent file")
            print("3. Use a VPN if your ISP blocks BitTorrent")
            print("4. Check if the torrent is still active (has seeders)")
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
            
    def stop(self):
        """Stop the client and clean up."""
        self.running = False
        for peer in list(self.active_peers.values()):
            peer.close()
        self.active_peers.clear()
        self.file_manager.close()
        
    def _handle_peer(self, peer):
        """Handle communication with a peer."""
        try:
            while self.running and not self.download_complete:
                peer.handle_messages()
        except Exception as e:
            logging.error(f"Peer error: {str(e)}")
        finally:
            peer.close()
            if (peer.host, peer.port) in self.active_peers:
                del self.active_peers[(peer.host, peer.port)]
                
    def _manage_downloads(self):
        """Manage piece requests and track progress."""
        total_pieces = self.torrent.num_pieces
        have_pieces = len(self.piece_manager.have_pieces)
        progress = (have_pieces / total_pieces) * 100 if total_pieces > 0 else 0
        
        # Calculate speed
        current_time = time.time()
        elapsed = current_time - self.start_time
        download_speed = self.downloaded / elapsed if elapsed > 0 else 0
        
        # Show progress
        logging.info(f"Progress: {progress:.2f}% ({have_pieces}/{total_pieces} pieces) - "
                    f"Speed: {download_speed/1024:.2f} KB/s")
        
        if have_pieces == total_pieces:
            logging.info("Download complete!")
            self.download_complete = True


        self.progress_thread = threading.Thread(target=self.show_progress)
        self.progress_thread.daemon = True  # Allow exit when main thread completes
        self.progress_thread.start()

        try:
            if self.seed:
                print("\n=== Starting BitTorrent Seeding ===")
                print(f"Torrent: {self.torrent.name}")
                print(f"Size: {Client.format_size(self.torrent.total_length)}")
                print(f"Pieces: {self.torrent.num_pieces} ({Client.format_size(self.torrent.piece_length)} each)")
                print(f"Local port: {self.port}")
                print(f"Peer ID: {self.peer_id.hex()}")
                
                # For seeding, assume files exist, load have_pieces
                for i in range(self.torrent.num_pieces):
                    self.piece_manager.have_pieces.add(i)
                    
                # Start seeding server
                self.seed_mode()
                print("\nSeeder initialized, waiting for connections...")
                
                # Keep running until Ctrl+C
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\nShutting down seeder...")
            else:
                self.leech_mode()
                
                # Wait for download completion or Ctrl+C
                try:
                    while not self.complete:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\nDownload interrupted...")
                    
                if self.complete:
                    print("\nDownload complete!")
        finally:
            # Clean up on exit
            self.file_manager.close()
            print("Client stopped.")

    def leech_mode(self):
        """Download mode."""
        print("\n=== Starting BitTorrent Download ===")
        print(f"Torrent: {self.torrent.name}")
        print(f"Size: {Client.format_size(self.torrent.total_length)}")
        print(f"Pieces: {self.torrent.num_pieces} ({Client.format_size(self.torrent.piece_length)} each)")
        print(f"Local port: {self.port}")
        print(f"Peer ID: {self.peer_id.hex()}")
        
        # Try local peers first
        local_peers = []
        for port in range(6881, 6890):
            if port != self.port:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    if sock.connect_ex(('127.0.0.1', port)) == 0:
                        local_peers.append(("127.0.0.1", port))
                    sock.close()
                except:
                    pass
        
        print(f"\nFound {len(local_peers)} active local peers")
        
        # Get peers from tracker
        print("\nContacting tracker for peer list...")
        tracker_peers = self.tracker.get_peers()
        
        # Combine local and tracker peers
        all_peers = list(set(local_peers + tracker_peers))  # Remove duplicates
        print(f"\nFound {len(all_peers)} total peers ({len(local_peers)} local, {len(tracker_peers)} from tracker)")
        
        active_peers = []
        for ip, port in all_peers:
            peer = Peer(ip, port, self.torrent, self.peer_id, self.piece_manager, is_seeding=False)
            try:
                peer.connect()
                print(f"Successfully connected to peer {ip}:{port}")
                active_peers.append(peer)
            except Exception as e:
                print(f"Failed to connect to {ip}:{port} - {str(e)}")
                continue
                
        if not active_peers:
            print("\nNo peers found! Cannot start download.")
            print("Possible issues:")
            print("1. No active seeders")
            print("2. Tracker connection failed")
            print("3. Firewall blocking BitTorrent traffic")
            print(f"4. Port {self.port} might be blocked")
            return

        max_peers = min(20, len(all_peers))  # Limit to 20 peers
        active_threads = []
        
        print(f"\nAttempting to connect to {max_peers} peers...")
        
        # Start peer connections
        for i, p in enumerate(all_peers[:max_peers]):
            try:
                print(f"\nConnecting to peer {i+1}/{max_peers}: {p[0]}:{p[1]}")
                peer = Peer(p[0], p[1], self.torrent, self.peer_id, self.piece_manager)
                t = threading.Thread(target=peer.connect, name=f"peer-{p[0]}:{p[1]}")
                t.start()
                active_threads.append(t)
                
                # Start in batches of 5 to avoid overwhelming the network
                if (i + 1) % 5 == 0:
                    print("\nWaiting for batch to connect...")
                    time.sleep(2)
            except Exception as e:
                print(f"\nError connecting to peer {p[0]}:{p[1]}: {str(e)}")
        
        # Wait for peer connections
        for t in active_threads:
            t.join(timeout=30)  # Don't wait forever for peers
            
        if not self.piece_manager.have_pieces:
            print("\nWarning: No pieces downloaded yet. Check if:")
            print("1. Trackers are responding")
            print("2. Peers are accessible (check your firewall)")
            print("3. The torrent has active seeders")
            
        if self.seed:
            seeding_thread = threading.Thread(target=self.seed_mode)
            seeding_thread.daemon = True
            seeding_thread.start()
            
        print("\nPeer connections established, download in progress...")

    def seed_mode(self):
        """Seeding mode: listen for incoming connections."""
        print("\n=== Starting BitTorrent Seeding ===")
        print(f"Torrent: {self.torrent.name}")
        print(f"Size: {Client.format_size(self.torrent.total_length)}")
        print(f"Pieces: {self.torrent.num_pieces} ({Client.format_size(self.torrent.piece_length)} each)")
        print(f"Local port: {self.port}")
        print(f"Peer ID: {self.peer_id.hex()}")

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            server.bind(('', self.port))
            server.listen(5)
            print("\nListening for peer connections...")
            
            # Register with tracker to allow peers to find us
            self.tracker.get_peers()  # This will register us with the tracker
            
            server.settimeout(1)  # Short timeout for responsive shutdown
            while True:  # Run indefinitely in seed mode
                try:
                    conn, addr = server.accept()
                    print(f"\nAccepted connection from {addr[0]}:{addr[1]}")
                    peer = Peer(addr[0], addr[1], self.torrent, self.peer_id, self.piece_manager, is_seeding=True)
                    t = threading.Thread(target=peer.handle_incoming, args=(conn,))
                    t.daemon = True
                    t.start()
                except socket.timeout:
                    continue
                except KeyboardInterrupt:
                    print("\nShutting down seeder...")
                    break
                except Exception as e:
                    print(f"\nError accepting connection: {e}")
                    continue
        finally:
            print("\nClosing seeding server...")
            server.close()

    def on_piece_verified(self, index):
        """Check if download complete."""
        if len(self.piece_manager.have_pieces) == self.torrent.num_pieces:
            self.complete = True

    def on_piece_requested(self, index, begin, length, peer):
        """Handle request during seeding."""
        if self.piece_manager.has_piece(index):
            block = self.piece_manager.get_block(index, begin, length)
            peer.send_piece(index, begin, block)

    @staticmethod
    def format_size(size):
        """Format size in bytes to human readable string."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.2f}{unit}"
            size /= 1024.0
        return f"{size:.2f}TB"

    def show_progress(self):
        """Display download progress with visual progress bar."""
        if self.seed:
            return  # No progress display needed for seeding
            
        import sys
        bar_length = 50  # Length of the progress bar
        last_downloaded = 0
        last_time = time.time()

        while not self.complete and self.running:
            try:
                current_time = time.time()
                total_pieces = self.torrent.num_pieces
                have_pieces = len(self.piece_manager.have_pieces)
                downloaded = have_pieces * self.torrent.piece_length
                
                # Calculate download speed
                speed = (downloaded - last_downloaded) / (current_time - last_time) if (current_time - last_time) > 0 else 0
                last_downloaded = downloaded
                last_time = current_time
                
                # Calculate progress percentage
                percent = have_pieces / total_pieces if total_pieces > 0 else 0
                filled_length = int(bar_length * percent)
                
                # Create the progress bar
                bar = '=' * filled_length + '-' * (bar_length - filled_length)
                
                # Format status line
                status_line = (
                    f"\rProgress: |{bar}| {percent*100:.1f}% "
                    f"({self.format_size(downloaded)}/{self.format_size(self.torrent.total_length)}) "
                    f"[{self.format_size(speed)}/s]"
                )
                
                # Display progress
                sys.stdout.write(status_line)
                sys.stdout.flush()
                
                time.sleep(1)
                
            except Exception as e:
                print(f"\nError updating progress display: {str(e)}")
                time.sleep(1)
                continue
                
        # Final newline after completion
        if self.complete:
            print("\nDownload complete!")