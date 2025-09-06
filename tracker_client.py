#!/usr/bin/env python3
"""
BitTorrent Tracker Communication

This module handles communication with HTTP/HTTPS and UDP trackers
following the BitTorrent protocol specifications.
"""

import struct
import socket
import urllib.parse
import urllib.request
import random
import time
import bcoding
import logging
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum


class TrackerEvent(Enum):
    """Tracker announce events."""
    NONE = 0
    COMPLETED = 1
    STARTED = 2
    STOPPED = 3


class TrackerResponse:
    """Represents a tracker response with peer list."""
    
    def __init__(self, response_data: Dict):
        self.interval = response_data.get('interval', 1800)
        self.complete = response_data.get('complete', 0)
        self.incomplete = response_data.get('incomplete', 0)
        self.peers = self._parse_peers(response_data.get('peers', []))
        self.failure_reason = response_data.get('failure reason')
        self.warning_message = response_data.get('warning message')
    
    def _parse_peers(self, peers_data) -> List[Tuple[str, int]]:
        """Parse peers from tracker response."""
        peers = []
        
        if isinstance(peers_data, bytes):
            # Compact format: 6 bytes per peer (4 bytes IP + 2 bytes port)
            for i in range(0, len(peers_data), 6):
                if i + 6 <= len(peers_data):
                    ip_bytes = peers_data[i:i+4]
                    port_bytes = peers_data[i+4:i+6]
                    
                    ip = '.'.join(str(b) for b in ip_bytes)
                    port = struct.unpack('>H', port_bytes)[0]
                    peers.append((ip, port))
        
        elif isinstance(peers_data, list):
            # Dictionary format
            for peer_dict in peers_data:
                if 'ip' in peer_dict and 'port' in peer_dict:
                    peers.append((peer_dict['ip'].decode('utf-8'), peer_dict['port']))
        
        return peers


class HTTPTracker:
    """HTTP/HTTPS tracker communication."""
    
    def __init__(self, announce_url: str, info_hash: bytes, peer_id: bytes):
        self.announce_url = announce_url
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.logger = logging.getLogger(__name__)
    
    def announce(self, port: int, uploaded: int = 0, downloaded: int = 0, 
                left: int = 0, event: TrackerEvent = TrackerEvent.NONE,
                num_want: int = 50, compact: bool = True) -> Optional[TrackerResponse]:
        """
        Send announce request to HTTP tracker.
        
        Args:
            port: Client listening port
            uploaded: Bytes uploaded
            downloaded: Bytes downloaded
            left: Bytes left to download
            event: Tracker event
            num_want: Number of peers requested
            compact: Use compact peer format
            
        Returns:
            TrackerResponse object or None if failed
        """
        try:
            params = {
                'info_hash': self.info_hash,
                'peer_id': self.peer_id,
                'port': port,
                'uploaded': uploaded,
                'downloaded': downloaded,
                'left': left,
                'compact': 1 if compact else 0,
                'numwant': num_want
            }
            
            if event != TrackerEvent.NONE:
                event_names = {
                    TrackerEvent.STARTED: 'started',
                    TrackerEvent.STOPPED: 'stopped',
                    TrackerEvent.COMPLETED: 'completed'
                }
                params['event'] = event_names[event]
            
            # URL encode parameters
            query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
            url = f"{self.announce_url}?{query_string}"
            
            self.logger.debug(f"Announcing to tracker: {self.announce_url}")
            
            # Make HTTP request
            request = urllib.request.Request(url)
            request.add_header('User-Agent', 'BitTorrent/Python-Client-1.0')
            
            with urllib.request.urlopen(request, timeout=30) as response:
                response_data = response.read()
                try:
                    decoded_response = bcoding.bdecode(response_data)
                except AttributeError:
                    try:
                        decoded_response = bcoding.decode(response_data)
                    except AttributeError:
                        import bencodepy
                        decoded_response = bencodepy.decode(response_data)
                
                if b'failure reason' in decoded_response:
                    self.logger.error(f"Tracker error: {decoded_response[b'failure reason'].decode('utf-8')}")
                    return None
                
                # Convert byte keys to string keys for easier handling
                response_dict = {}
                for key, value in decoded_response.items():
                    if isinstance(key, bytes):
                        key = key.decode('utf-8')
                    if isinstance(value, bytes) and key not in ['peers']:
                        try:
                            value = value.decode('utf-8')
                        except UnicodeDecodeError:
                            pass
                    response_dict[key] = value
                
                return TrackerResponse(response_dict)
                
        except Exception as e:
            self.logger.error(f"HTTP tracker announce failed: {e}")
            return None


class UDPTracker:
    """UDP tracker communication."""
    
    def __init__(self, announce_url: str, info_hash: bytes, peer_id: bytes):
        self.announce_url = announce_url
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.connection_id = None
        self.logger = logging.getLogger(__name__)
        
        # Parse UDP URL
        parsed = urllib.parse.urlparse(announce_url)
        self.host = parsed.hostname
        self.port = parsed.port or 80
    
    def _send_udp_request(self, data: bytes, timeout: int = 15) -> Optional[bytes]:
        """Send UDP request and receive response."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            
            sock.sendto(data, (self.host, self.port))
            response, _ = sock.recvfrom(1024)
            sock.close()
            
            return response
        except Exception as e:
            self.logger.error(f"UDP request failed: {e}")
            return None
    
    def _connect(self) -> bool:
        """Establish connection with UDP tracker."""
        # Connection request format:
        # 8 bytes: protocol_id (0x41727101980)
        # 4 bytes: action (0 = connect)
        # 4 bytes: transaction_id
        
        protocol_id = 0x41727101980
        action = 0  # Connect
        transaction_id = random.randint(0, 2**32 - 1)
        
        request = struct.pack('>QII', protocol_id, action, transaction_id)
        
        response = self._send_udp_request(request)
        if not response or len(response) < 16:
            self.logger.error("Invalid connect response from UDP tracker")
            return False
        
        # Parse response
        resp_action, resp_transaction_id, connection_id = struct.unpack('>III', response[:12])
        
        if resp_action != 0 or resp_transaction_id != transaction_id:
            self.logger.error("Invalid connect response format")
            return False
        
        self.connection_id = connection_id
        self.logger.debug("UDP tracker connection established")
        return True
    
    def announce(self, port: int, uploaded: int = 0, downloaded: int = 0,
                left: int = 0, event: TrackerEvent = TrackerEvent.NONE,
                num_want: int = 50) -> Optional[TrackerResponse]:
        """
        Send announce request to UDP tracker.
        
        Returns:
            TrackerResponse object or None if failed
        """
        # Connect if not already connected
        if self.connection_id is None:
            if not self._connect():
                return None
        
        try:
            # Announce request format:
            # 8 bytes: connection_id
            # 4 bytes: action (1 = announce)
            # 4 bytes: transaction_id
            # 20 bytes: info_hash
            # 20 bytes: peer_id
            # 8 bytes: downloaded
            # 8 bytes: left
            # 8 bytes: uploaded
            # 4 bytes: event
            # 4 bytes: IP (0 = default)
            # 4 bytes: key (random)
            # 4 bytes: num_want
            # 2 bytes: port
            
            action = 1  # Announce
            transaction_id = random.randint(0, 2**32 - 1)
            ip = 0  # Use default IP
            key = random.randint(0, 2**32 - 1)
            
            request = struct.pack('>QII20s20sQQQIIIIH',
                                self.connection_id, action, transaction_id,
                                self.info_hash, self.peer_id,
                                downloaded, left, uploaded,
                                event.value, ip, key, num_want, port)
            
            response = self._send_udp_request(request)
            if not response or len(response) < 20:
                self.logger.error("Invalid announce response from UDP tracker")
                return None
            
            # Parse response
            resp_action, resp_transaction_id, interval, leechers, seeders = struct.unpack('>IIIII', response[:20])
            
            if resp_action != 1 or resp_transaction_id != transaction_id:
                self.logger.error("Invalid announce response format")
                return None
            
            # Parse peers (6 bytes per peer: 4 bytes IP + 2 bytes port)
            peers_data = response[20:]
            
            response_dict = {
                'interval': interval,
                'complete': seeders,
                'incomplete': leechers,
                'peers': peers_data
            }
            
            return TrackerResponse(response_dict)
            
        except Exception as e:
            self.logger.error(f"UDP tracker announce failed: {e}")
            return None


class TrackerManager:
    """Manages communication with multiple trackers."""
    
    def __init__(self, announce_urls: List[str], info_hash: bytes, peer_id: bytes):
        self.announce_urls = announce_urls
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.trackers = []
        self.logger = logging.getLogger(__name__)
        
        # Initialize trackers
        for url in announce_urls:
            if url.startswith('http://') or url.startswith('https://'):
                self.trackers.append(HTTPTracker(url, info_hash, peer_id))
            elif url.startswith('udp://'):
                self.trackers.append(UDPTracker(url, info_hash, peer_id))
            else:
                self.logger.warning(f"Unsupported tracker URL: {url}")
    
    def announce_to_all(self, port: int, uploaded: int = 0, downloaded: int = 0,
                       left: int = 0, event: TrackerEvent = TrackerEvent.NONE,
                       num_want: int = 50) -> List[TrackerResponse]:
        """
        Announce to all trackers and return successful responses.
        
        Returns:
            List of successful TrackerResponse objects
        """
        responses = []
        
        for tracker in self.trackers:
            try:
                response = tracker.announce(port, uploaded, downloaded, left, event, num_want)
                if response:
                    responses.append(response)
                    self.logger.debug(f"Successful announce to {tracker.announce_url}")
                else:
                    self.logger.warning(f"Failed announce to {tracker.announce_url}")
            except Exception as e:
                self.logger.error(f"Error announcing to {tracker.announce_url}: {e}")
        
        return responses
    
    def get_peers(self, port: int, uploaded: int = 0, downloaded: int = 0,
                  left: int = 0, event: TrackerEvent = TrackerEvent.NONE) -> List[Tuple[str, int]]:
        """
        Get peers from all trackers.
        
        Returns:
            List of unique peer tuples (ip, port)
        """
        all_peers = []
        responses = self.announce_to_all(port, uploaded, downloaded, left, event)
        
        for response in responses:
            all_peers.extend(response.peers)
        
        # Remove duplicates
        unique_peers = list(set(all_peers))
        self.logger.info(f"Got {len(unique_peers)} unique peers from {len(responses)} trackers")
        
        return unique_peers


if __name__ == "__main__":
    # Test tracker functionality
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python tracker_client.py <torrent_file>")
        sys.exit(1)
    
    logging.basicConfig(level=logging.DEBUG)
    
    # Parse torrent to get announce URLs and info hash
    from torrent_new import parse_torrent
    
    try:
        torrent = parse_torrent(sys.argv[1])
        peer_id = b'-PC0001-' + bytes([random.randint(0, 255) for _ in range(12)])
        
        tracker_manager = TrackerManager(torrent.announce_list, torrent.info_hash, peer_id)
        peers = tracker_manager.get_peers(6881, left=torrent.total_size, event=TrackerEvent.STARTED)
        
        print(f"Found {len(peers)} peers:")
        for i, (ip, port) in enumerate(peers[:10]):  # Show first 10 peers
            print(f"  {i+1}. {ip}:{port}")
        
        if len(peers) > 10:
            print(f"  ... and {len(peers) - 10} more")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
