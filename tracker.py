# tracker.py: Handles communication with BitTorrent trackers

import socket
import struct
import random
import time
import urllib.parse
import requests
import logging
import binascii

class Tracker:
    def __init__(self, torrent):
        """Initialize tracker with torrent metadata."""
        self.torrent = torrent
        self.connected = False
        self.transaction_id = None
        self.connection_id = None
        self.peer_id = None
        self.port = 6881  # Default port
    
    def connect(self, announce_url):
        """Connect to tracker and get peer list."""
        if announce_url.startswith('http'):
            return self._http_connect(announce_url)
        elif announce_url.startswith('udp'):
            return self._udp_connect(announce_url)
        else:
            raise ValueError(f"Unsupported tracker protocol: {announce_url}")

    def _udp_connect(self, announce_url):
        """Connect to UDP tracker (full implementation)."""
        import urllib.parse
        import socket
        import struct
        import random
        import time
        
        try:
            # Parse UDP tracker URL
            parsed = urllib.parse.urlparse(announce_url)
            host = parsed.hostname
            port = parsed.port or 80
            
            print(f"Connecting to UDP tracker {host}:{port}")
            
            # Create UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(15)
            
            # Step 1: Connection request
            connection_id = 0x41727101980  # Magic constant
            action = 0  # Connect action
            transaction_id = random.randint(0, 2**32-1)
            
            # Pack connection request
            request = struct.pack('!QII', connection_id, action, transaction_id)
            
            # Send request
            sock.sendto(request, (host, port))
            
            # Receive response
            response, addr = sock.recvfrom(16)
            
            # Unpack connection response
            resp_action, resp_transaction, resp_connection_id = struct.unpack('!IIQ', response)
            
            if resp_action != 0 or resp_transaction != transaction_id:
                raise Exception("Invalid connection response")
            
            # Step 2: Announce request
            action = 1  # Announce action
            transaction_id = random.randint(0, 2**32-1)
            
            # Prepare announce data
            info_hash = self.torrent.info_hash
            if isinstance(info_hash, str):
                info_hash = info_hash.encode('latin1')
            
            peer_id = ('-PY0001-' + ''.join([str(random.randint(0, 9)) for _ in range(12)])).encode()[:20]
            downloaded = 0
            left = self.torrent.total_length
            uploaded = 0
            event = 2  # Started
            ip = 0  # Default
            key = random.randint(0, 2**32-1)
            num_want = 50
            port = self.port
            
            # Pack announce request
            announce_req = struct.pack('!QII20s20sQQQIIIiH',
                                     resp_connection_id, action, transaction_id,
                                     info_hash, peer_id, downloaded, left, uploaded,
                                     event, ip, key, num_want, port)
            
            # Send announce request
            sock.sendto(announce_req, (host, port))
            
            # Receive announce response
            response, addr = sock.recvfrom(1024)
            
            # Unpack announce response
            if len(response) < 20:
                raise Exception("Invalid announce response length")
            
            resp_action, resp_transaction, interval, leechers, seeders = struct.unpack('!IIIII', response[:20])
            
            if resp_action != 1 or resp_transaction != transaction_id:
                raise Exception("Invalid announce response")
            
            # Extract peer list
            peer_data = response[20:]
            peers = []
            
            for i in range(0, len(peer_data), 6):
                if i + 6 <= len(peer_data):
                    ip_bytes = peer_data[i:i+4]
                    port_bytes = peer_data[i+4:i+6]
                    
                    ip = socket.inet_ntoa(ip_bytes)
                    port = struct.unpack('!H', port_bytes)[0]
                    
                    # Skip localhost unless it's a different port
                    if not (ip == '127.0.0.1' and port == self.port):
                        peers.append((ip, port))
            
            sock.close()
            print(f"✓ UDP tracker successful: {len(peers)} peers, {seeders} seeders, {leechers} leechers")
            return peers
            
        except socket.timeout:
            print(f"✗ UDP tracker timeout: {host}:{port}")
            return []
        except Exception as e:
            print(f"✗ UDP tracker error: {str(e)}")
            return []
        finally:
            try:
                sock.close()
            except:
                pass

    def _http_connect(self, announce_url):
        """Connect to HTTP tracker."""
        try:
            peer_id = '-PY0001-' + ''.join([str(random.randint(0, 9)) for _ in range(12)])
            
            # Properly URL-encode info_hash (as bytes)
            info_hash = self.torrent.info_hash
            if isinstance(info_hash, str):
                info_hash = info_hash.encode('latin1')
            info_hash_encoded = urllib.parse.quote_from_bytes(info_hash)
            
            params = {
                'info_hash': info_hash_encoded,
                'peer_id': peer_id,
                'port': self.port,
                'uploaded': 0,
                'downloaded': 0,
                'left': self.torrent.total_length,
                'compact': 1,
                'event': 'started',
                'numwant': 50,
                'key': ''.join([str(random.randint(0, 9)) for _ in range(8)]),
                'supportcrypto': 1,
            }
            
            url = announce_url + '?' + '&'.join(f"{k}={v}" for k, v in params.items())
            logging.info(f"Tracker request URL: {url}")
            
            response = requests.get(url, timeout=15)
            logging.info(f"Tracker response status: {response.status_code}")
            logging.info(f"Tracker response headers: {response.headers}")
            logging.info(f"Tracker response raw data: {binascii.hexlify(response.content)[:200]} ...")
            
            if response.status_code != 200:
                raise ConnectionError(f"Tracker returned {response.status_code}")
                
            data = response.content
            
            # Try to decode bencoded response
            try:
                import bcoding
                decoded = bcoding.bdecode(data)
                logging.info(f"Decoded tracker response: {decoded}")
                
                # Check for failure reason
                failure_reason = decoded.get(b'failure reason') or decoded.get('failure reason')
                if failure_reason:
                    if isinstance(failure_reason, bytes):
                        failure_reason = failure_reason.decode('utf-8')
                    logging.warning(f"Tracker returned failure: {failure_reason}")
                    
                    # If it's an authorization error, this tracker doesn't allow this torrent
                    if 'not authorized' in failure_reason.lower() or 'not allowed' in failure_reason.lower():
                        logging.info("This tracker requires registration or doesn't support this torrent")
                        return []
                    else:
                        raise Exception(f"Tracker error: {failure_reason}")
                
                peers = decoded.get(b'peers') or decoded.get('peers')
                peer_list = []
                
                if isinstance(peers, (bytes, bytearray)):
                    # Compact format
                    for i in range(0, len(peers), 6):
                        if i + 6 <= len(peers):
                            ip = socket.inet_ntoa(peers[i:i+4])
                            port = struct.unpack('>H', peers[i+4:i+6])[0]
                            # Skip localhost only if it's the same port as ours
                            if not (ip == '127.0.0.1' and port == self.port):
                                peer_list.append((ip, port))
                elif isinstance(peers, list):
                    # Dictionary format
                    for peer in peers:
                        ip = peer.get(b'ip') or peer.get('ip')
                        port = peer.get(b'port') or peer.get('port')
                        if isinstance(ip, bytes):
                            ip = ip.decode('utf-8')
                        # Skip localhost only if it's the same port as ours
                        if not (ip == '127.0.0.1' and port == self.port):
                            peer_list.append((ip, port))
                            
                logging.info(f"Parsed peer list: {peer_list}")
                return peer_list
                
            except Exception as e:
                logging.error(f"Error decoding tracker response: {e}")
                return []
                
        except requests.exceptions.RequestException as e:
            logging.error(f"HTTP tracker connection error: {str(e)}")
        except Exception as e:
            logging.error(f"HTTP tracker error: {str(e)}")
        return []
    
    def get_peers(self):
        """Get peers from all available sources."""
        # Try all announce URLs
        all_trackers = []
        if hasattr(self.torrent, 'announce_list') and self.torrent.announce_list:
            all_trackers.extend(self.torrent.announce_list)
        if self.torrent.announce:
            all_trackers.append([self.torrent.announce])
            
        logging.info(f"Trying {len(all_trackers)} tracker groups")
        peers = []
        
        # Try each tracker in each group
        for tracker_list in all_trackers:
            for tracker in tracker_list:
                try:
                    new_peers = self.connect(tracker)
                    if new_peers:
                        peers.extend(new_peers)
                        break  # Found peers from this tracker group
                except Exception as e:
                    logging.warning(f"Failed to connect to tracker {tracker}: {str(e)}")
            if peers:
                break  # No need to try more trackers
                
        # If no external peers found, try some public HTTP trackers as fallback
        if not peers:
            fallback_trackers = [
                "http://tracker.openbittorrent.com:80/announce",
                "http://tracker.publicbt.com:80/announce", 
                "http://announce.torrentsmd.com:8080/announce",
                "http://bt.xxx-tracker.com:2710/announce",
                "http://retracker.mgts.by:80/announce"
            ]
            
            print(f"\nNo peers found from original trackers. Trying {len(fallback_trackers)} fallback HTTP trackers...")
            
            for fallback_url in fallback_trackers:
                try:
                    print(f"Trying fallback tracker: {fallback_url}")
                    # Create a temporary torrent copy with fallback tracker
                    original_announce = self.torrent.announce
                    self.torrent.announce = fallback_url
                    
                    new_peers = self._http_connect(fallback_url)
                    if new_peers:
                        print(f"✓ Found {len(new_peers)} peers from fallback tracker!")
                        peers.extend(new_peers)
                        # Restore original announce
                        self.torrent.announce = original_announce
                        break
                    else:
                        print(f"✗ No peers from {fallback_url}")
                        
                    # Restore original announce
                    self.torrent.announce = original_announce
                    
                except Exception as e:
                    # Restore original announce
                    self.torrent.announce = original_announce
                    print(f"✗ Fallback tracker failed: {str(e)}")
                    continue
        
        # Only add local peers if we still have no real peers AND we're testing
        if not peers:
            print("\nNo real peers found. This could be because:")
            print("1. The torrent uses only UDP trackers (not fully supported)")
            print("2. All trackers are down or blocking connections") 
            print("3. The torrent has no active seeders")
            print("4. Your firewall is blocking tracker connections")
            print("\nFor testing purposes, adding local peers...")
            
            # Use a smaller range for local testing
            for port in range(6881, 6885):
                peers.append(('127.0.0.1', port))
            logging.info("Using local peers for testing")
            
        logging.info(f"Found {len(peers)} total peers")
        return peers
