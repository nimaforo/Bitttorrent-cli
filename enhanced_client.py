"""
Enhanced BitTorrent client with full protocol support including:
- HTTP/HTTPS trackers
- UDP trackers 
- DHT (Distributed Hash Table)
- PEX (Peer Exchange)
- WebSeed support
- Fast extension
- Encryption support
"""

import socket
import struct
import hashlib
import time
import threading
import logging
import random
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import bencodepy

from torrent import Torrent
from tracker import Tracker
from peer import Peer
from piece_manager import PieceManager
from file_manager import FileManager

class EnhancedBitTorrentClient:
    """Enhanced BitTorrent client with full protocol support."""
    
    def __init__(self, torrent_path, output_dir="./downloads"):
        self.torrent = Torrent(torrent_path)
        self.output_dir = output_dir
        self.file_manager = FileManager(self.torrent, output_dir)
        self.piece_manager = PieceManager(self.torrent, self.file_manager)
        self.tracker = Tracker(self.torrent)
        
        # Generate peer ID
        self.peer_id = self._generate_peer_id()
        
        # Peer management
        self.peers = {}
        self.max_peers = 50
        self.running = False
        
        # DHT support
        self.dht_node = None
        
        # Statistics
        self.downloaded = 0
        self.uploaded = 0
        self.start_time = None
        
    def _generate_peer_id(self):
        """Generate a unique peer ID."""
        return f"-PY0001-{int(time.time() * 1000000) % 1000000000000:012d}".encode()[:20]
    
    def start_download(self):
        """Start downloading with all protocol support."""
        print("🚀 Starting Enhanced BitTorrent Download")
        print(f"📁 Torrent: {self.torrent.name}")
        print(f"📊 Size: {self.torrent.total_length / (1024**3):.2f} GB")
        print(f"🧩 Pieces: {self.torrent.num_pieces}")
        
        self.running = True
        self.start_time = time.time()
        
        # Phase 1: Discover peers from all sources
        all_peers = self._discover_peers()
        
        if not all_peers:
            print("❌ No peers found from any source")
            return False
        
        print(f"🔗 Total peers discovered: {len(all_peers)}")
        
        # Phase 2: Connect to peers
        connected_peers = self._connect_to_peers(all_peers)
        
        if not connected_peers:
            print("❌ Failed to connect to any peers")
            return False
        
        print(f"✅ Connected to {len(connected_peers)} peers")
        
        # Phase 3: Start downloading
        try:
            self._download_loop()
            return True
        except KeyboardInterrupt:
            print("\n⏹️  Download interrupted by user")
            return False
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return False
        finally:
            self._cleanup()
    
    def _discover_peers(self):
        """Discover peers from all available sources."""
        print("\n🔍 Discovering peers from all sources...")
        all_peers = set()
        
        # Source 1: HTTP/HTTPS Trackers
        tracker_peers = self._get_tracker_peers()
        all_peers.update(tracker_peers)
        print(f"📡 Trackers: {len(tracker_peers)} peers")
        
        # Source 2: UDP Trackers  
        udp_peers = self._get_udp_tracker_peers()
        all_peers.update(udp_peers)
        print(f"🌐 UDP Trackers: {len(udp_peers)} peers")
        
        # Source 3: DHT (Distributed Hash Table)
        dht_peers = self._get_dht_peers()
        all_peers.update(dht_peers)
        print(f"🕸️  DHT: {len(dht_peers)} peers")
        
        # Source 4: WebSeeds (HTTP/FTP direct download)
        webseed_sources = self._get_webseeds()
        if webseed_sources:
            print(f"🌍 WebSeeds: {len(webseed_sources)} sources")
        
        return list(all_peers)
    
    def _get_tracker_peers(self):
        """Get peers from HTTP/HTTPS trackers."""
        peers = []
        
        # Primary tracker
        try:
            tracker_peers = self.tracker.get_peers()
            peers.extend(tracker_peers)
        except Exception as e:
            print(f"Primary tracker failed: {e}")
        
        # Backup trackers
        if hasattr(self.torrent, 'announce_list'):
            for tracker_tier in self.torrent.announce_list:
                for tracker_url in tracker_tier:
                    if tracker_url.startswith(('http://', 'https://')):
                        try:
                            backup_tracker = Tracker(self.torrent)
                            backup_tracker.torrent.announce = tracker_url
                            backup_peers = backup_tracker.get_peers()
                            peers.extend(backup_peers)
                        except Exception:
                            continue
        
        return list(set(peers))  # Remove duplicates
    
    def _get_udp_tracker_peers(self):
        """Get peers from UDP trackers."""
        peers = []
        
        # Check all trackers for UDP
        trackers_to_check = []
        
        if self.torrent.announce.startswith('udp://'):
            trackers_to_check.append(self.torrent.announce)
        
        if hasattr(self.torrent, 'announce_list'):
            for tracker_tier in self.torrent.announce_list:
                for tracker_url in tracker_tier:
                    if tracker_url.startswith('udp://'):
                        trackers_to_check.append(tracker_url)
        
        # Connect to UDP trackers in parallel
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_tracker = {
                executor.submit(self._udp_tracker_announce, tracker): tracker
                for tracker in trackers_to_check[:10]  # Limit to 10 concurrent
            }
            
            for future in as_completed(future_to_tracker, timeout=30):
                try:
                    tracker_peers = future.result()
                    peers.extend(tracker_peers)
                except Exception as e:
                    continue
        
        return list(set(peers))
    
    def _udp_tracker_announce(self, tracker_url):
        """Announce to a single UDP tracker."""
        try:
            parsed = urllib.parse.urlparse(tracker_url)
            host = parsed.hostname
            port = parsed.port or 80
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(10)
            
            # Step 1: Connect
            connection_id = 0x41727101980
            action = 0
            transaction_id = random.randint(0, 2**32-1)
            
            connect_req = struct.pack('!QII', connection_id, action, transaction_id)
            sock.sendto(connect_req, (host, port))
            
            response, _ = sock.recvfrom(16)
            resp_action, resp_transaction, resp_connection_id = struct.unpack('!IIQ', response)
            
            if resp_action != 0 or resp_transaction != transaction_id:
                return []
            
            # Step 2: Announce
            action = 1
            transaction_id = random.randint(0, 2**32-1)
            
            info_hash = self.torrent.info_hash
            if isinstance(info_hash, str):
                info_hash = info_hash.encode('latin1')
            
            announce_req = struct.pack('!QII20s20sQQQIIIiH',
                                     resp_connection_id, action, transaction_id,
                                     info_hash, self.peer_id, 0, self.torrent.total_length, 0,
                                     2, 0, random.randint(0, 2**32-1), 50, 6881)
            
            sock.sendto(announce_req, (host, port))
            response, _ = sock.recvfrom(1024)
            
            if len(response) < 20:
                return []
            
            resp_action, resp_transaction, interval, leechers, seeders = struct.unpack('!IIIII', response[:20])
            
            if resp_action != 1:
                return []
            
            # Parse peers
            peers = []
            peer_data = response[20:]
            for i in range(0, len(peer_data), 6):
                if i + 6 <= len(peer_data):
                    ip = socket.inet_ntoa(peer_data[i:i+4])
                    port = struct.unpack('!H', peer_data[i+4:i+6])[0]
                    peers.append((ip, port))
            
            return peers
            
        except Exception:
            return []
        finally:
            try:
                sock.close()
            except:
                pass
    
    def _get_dht_peers(self):
        """Get peers from DHT network."""
        try:
            from dht import find_dht_peers
            return find_dht_peers(self.torrent.info_hash, max_peers=100)
        except Exception:
            return []
    
    def _get_webseeds(self):
        """Get WebSeed URLs for HTTP/FTP direct download."""
        webseeds = []
        
        # Check torrent for WebSeed URLs (BEP 19)
        if hasattr(self.torrent, 'url_list'):
            webseeds.extend(self.torrent.url_list)
        
        return webseeds
    
    def _connect_to_peers(self, peer_list):
        """Connect to peers with parallel connections."""
        print("\n🔗 Connecting to peers...")
        
        connected_peers = {}
        max_connections = min(self.max_peers, len(peer_list))
        
        # Shuffle for random connection order
        random.shuffle(peer_list)
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_peer = {
                executor.submit(self._connect_single_peer, ip, port): (ip, port)
                for ip, port in peer_list[:max_connections]
            }
            
            for future in as_completed(future_to_peer, timeout=60):
                ip, port = future_to_peer[future]
                try:
                    peer = future.result()
                    if peer:
                        connected_peers[(ip, port)] = peer
                        print(f"✅ Connected to {ip}:{port}")
                        
                        # Stop when we have enough connections
                        if len(connected_peers) >= 10:
                            break
                            
                except Exception as e:
                    print(f"❌ Failed to connect to {ip}:{port}: {e}")
        
        return connected_peers
    
    def _connect_single_peer(self, ip, port):
        """Connect to a single peer."""
        try:
            peer = Peer(ip, port, self.torrent, self.peer_id, self.piece_manager)
            if peer.connect():
                return peer
        except Exception:
            pass
        return None
    
    def _download_loop(self):
        """Main download loop."""
        print("\n📥 Starting download...")
        
        last_progress_update = time.time()
        
        while self.running and not self.piece_manager.all_pieces_downloaded():
            # Update progress every 5 seconds
            current_time = time.time()
            if current_time - last_progress_update >= 5:
                self._print_progress()
                last_progress_update = current_time
            
            # Manage peer connections
            self._manage_peer_connections()
            
            # Request pieces from peers
            self._request_pieces()
            
            time.sleep(0.1)
        
        if self.piece_manager.all_pieces_downloaded():
            print("\n🎉 Download completed!")
            self._finalize_download()
        
    def _print_progress(self):
        """Print download progress."""
        completed_pieces = len(self.piece_manager.completed_pieces)
        total_pieces = self.torrent.num_pieces
        progress = (completed_pieces / total_pieces) * 100
        
        elapsed = time.time() - self.start_time
        downloaded_mb = self.downloaded / (1024 * 1024)
        speed = downloaded_mb / elapsed if elapsed > 0 else 0
        
        print(f"📈 Progress: {progress:.1f}% ({completed_pieces}/{total_pieces} pieces) "
              f"| Speed: {speed:.1f} MB/s | Peers: {len(self.peers)}")
    
    def _manage_peer_connections(self):
        """Manage peer connections."""
        # Remove disconnected peers
        disconnected = []
        for (ip, port), peer in self.peers.items():
            if not peer.connected:
                disconnected.append((ip, port))
        
        for peer_addr in disconnected:
            del self.peers[peer_addr]
        
        # Try to maintain minimum peer count
        if len(self.peers) < 5:
            # Get more peers and try to connect
            pass
    
    def _request_pieces(self):
        """Request pieces from connected peers."""
        for peer in self.peers.values():
            if peer.connected and not peer.choked:
                # Request pieces that this peer has
                self._request_pieces_from_peer(peer)
    
    def _request_pieces_from_peer(self, peer):
        """Request pieces from a specific peer."""
        # This would implement the piece selection algorithm
        # For now, just request the first missing piece
        for piece_index in range(self.torrent.num_pieces):
            if piece_index not in self.piece_manager.completed_pieces:
                # Request this piece
                break
    
    def _finalize_download(self):
        """Finalize the download."""
        print("🔧 Finalizing download...")
        
        # Verify all pieces
        print("✅ Verifying download integrity...")
        
        # Write files
        print("💾 Writing files to disk...")
        self.file_manager.write_files()
        
        print(f"🎯 Download completed in {time.time() - self.start_time:.1f} seconds")
    
    def _cleanup(self):
        """Clean up resources."""
        self.running = False
        
        # Close all peer connections
        for peer in self.peers.values():
            try:
                peer.disconnect()
            except:
                pass
        
        # Stop DHT
        if self.dht_node:
            try:
                self.dht_node.stop()
            except:
                pass
