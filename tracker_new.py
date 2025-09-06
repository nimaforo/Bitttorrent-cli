# tracker.py: Handles communication with BitTorrent trackers

import socket
import struct
import random
import time
from urllib.parse import urlencode, quote
import requests
from utils import bdecode

class Tracker:
    def __init__(self, torrent, peer_id, port, compact=1):
        self.torrent = torrent
        self.peer_id = peer_id
        self.port = port
        self.compact = compact
        self.max_retries = 3
        self.retry_delay = 5
        self.active_peers = set()
        
    def _try_tracker(self, tracker_url):
        """Try to get peers from a single tracker."""
        # Convert tracker URL to string if it's bytes
        if isinstance(tracker_url, bytes):
            tracker_url = tracker_url.decode('utf-8')
            
        # Prepare parameters with proper encoding
        params = {
            'info_hash': quote(self.torrent.info_hash),  # URL encode the info_hash
            'peer_id': quote(self.peer_id),  # URL encode the peer_id
            'port': self.port,
            'uploaded': 0,
            'downloaded': 0,
            'left': self.torrent.total_length,
            'event': 'started',
            'compact': self.compact,
            'numwant': 50,
            'supportcrypto': 1,
            'key': ''.join([str(random.randint(0, 9)) for _ in range(8)])  # Random key for unique client ID
        }
        
        try:
            print(f"\nTrying tracker: {tracker_url}")
            headers = {
                'User-Agent': 'BitTorrent/7.11.1',  # Standard BitTorrent client UA
                'Accept-Encoding': 'gzip'
            }
            
            # Construct full URL with properly encoded parameters
            full_url = tracker_url + '?' + urlencode(params)
            r = requests.get(
                full_url,
                headers=headers,
                timeout=10
            )
            if r.status_code != 200:
                print(f"Tracker returned {r.status_code}")
                return False
            response = bdecode(r.content)
            if b'failure reason' in response:
                print(f"Tracker failure: {response[b'failure reason'].decode('utf-8')}")
                return False
            if b'peers' in response:
                peers = response[b'peers']
                print(f"\nReceived {len(peers)} bytes of peer data")
                
                if isinstance(peers, bytes):  # Compact format
                    for i in range(0, len(peers), 6):
                        ip = socket.inet_ntoa(peers[i:i+4])
                        port = struct.unpack(">H", peers[i+4:i+6])[0]
                        if ip != "127.0.0.1":  # Skip localhost peers
                            print(f"Found peer: {ip}:{port}")
                            self.active_peers.add((ip, port))
                            
                elif isinstance(peers, list):  # Dictionary format
                    for peer in peers:
                        ip = peer[b'ip'].decode('utf-8')
                        port = peer[b'port']
                        if ip != "127.0.0.1":  # Skip localhost peers
                            print(f"Found peer: {ip}:{port}")
                            self.active_peers.add((ip, port))
                            
            return len(self.active_peers) > 0
            
        except Exception as e:
            print(f"\nTracker error ({tracker_url}): {str(e)}")
        return False
    
    def get_peers(self):
        """Get peers from all available sources."""
        # Try all announce URLs
        all_trackers = []
        if hasattr(self.torrent, 'announce_list') and self.torrent.announce_list:
            all_trackers.extend(self.torrent.announce_list)
        if self.torrent.announce:
            all_trackers.append([self.torrent.announce])
            
        print(f"\nTrying {len(all_trackers)} tracker groups")
        found_peers = False
        
        # Try each tracker in each group
        for tracker_list in all_trackers:
            for tracker in tracker_list:
                if self._try_tracker(tracker):
                    found_peers = True
                    break  # Found peers from this tracker group
            if found_peers:
                break  # No need to try more trackers
                
        # If no external peers found, use local peers as fallback
        if not self.active_peers:
            print("\nNo external peers found, using local peers for testing")
            # Use a wider port range for testing
            for port in range(6881, 6900):
                if port != self.port:  # Don't connect to self
                    self.active_peers.add(("127.0.0.1", port))
                    
        print(f"\nFound {len(self.active_peers)} total peers")
        return list(self.active_peers)
