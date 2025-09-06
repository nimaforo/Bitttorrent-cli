"""
BitTorrent Tracker Communication

This module handles communication with BitTorrent trackers according to the
BitTorrent protocol specification. It supports both HTTP/HTTPS and UDP trackers
with proper announce/scrape functionality.

Author: BitTorrent CLI Client
"""

import struct
import socket
import random
import time
import urllib.parse
import urllib.request
import logging
from typing import List, Tuple, Optional, Dict, Any
import bcoding
import ipaddress


class TrackerError(Exception):
    """Exception raised for tracker-related errors."""
    pass


class HTTPTracker:
    """
    HTTP/HTTPS BitTorrent tracker communication.
    
    Implements the HTTP tracker protocol as specified in BEP 3.
    """
    
    def __init__(self, announce_url: str, info_hash: bytes, peer_id: bytes, port: int):
        """
        Initialize HTTP tracker.
        
        Args:
            announce_url: Tracker announce URL
            info_hash: 20-byte SHA1 hash of torrent info dict
            peer_id: 20-byte peer ID
            port: Port number for incoming connections
        """
        self.announce_url = announce_url
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.port = port
        self.tracker_id = None
        self.interval = 1800  # Default announce interval (30 minutes)
        self.min_interval = 900  # Minimum announce interval (15 minutes)
        
        # Statistics
        self.uploaded = 0
        self.downloaded = 0
        self.left = 0
        
        # Setup logging
        self.logger = logging.getLogger(f"HTTPTracker({announce_url})")
    
    def announce(self, event: str = None, numwant: int = 50, 
                compact: bool = True) -> Dict[str, Any]:
        """
        Send announce request to tracker.
        
        Args:
            event: Event type ('started', 'stopped', 'completed', or None)
            numwant: Number of peers requested
            compact: Use compact peer list format
            
        Returns:
            Dictionary containing tracker response
            
        Raises:
            TrackerError: If announce request fails
        """
        try:
            # Build announce URL
            params = {
                'info_hash': self.info_hash,
                'peer_id': self.peer_id,
                'port': self.port,
                'uploaded': self.uploaded,
                'downloaded': self.downloaded,
                'left': self.left,
                'compact': 1 if compact else 0,
                'numwant': numwant,
                'key': random.randint(0, 2**32 - 1),
                'supportcrypto': 1
            }
            
            if event:
                params['event'] = event
            
            if self.tracker_id:
                params['trackerid'] = self.tracker_id
            
            # URL encode parameters
            query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
            
            # Handle URL separator
            separator = '&' if '?' in self.announce_url else '?'
            full_url = f"{self.announce_url}{separator}{query_string}"
            
            self.logger.debug(f"Announcing to tracker: {full_url}")
            
            # Make HTTP request
            request = urllib.request.Request(full_url)
            request.add_header('User-Agent', 'BitTorrent-CLI-Client/1.0')
            
            with urllib.request.urlopen(request, timeout=30) as response:
                response_data = response.read()
            
            # Decode bencoded response
            try:
                decoded_response = bcoding.bdecode(response_data)
            except Exception as e:
                raise TrackerError(f"Invalid tracker response: {e}")
            
            # Check for tracker error
            if b'failure reason' in decoded_response:
                reason = decoded_response[b'failure reason'].decode('utf-8', errors='replace')
                raise TrackerError(f"Tracker error: {reason}")
            
            # Parse successful response
            response_dict = self._parse_announce_response(decoded_response)
            
            # Update tracker state
            self.interval = response_dict.get('interval', self.interval)
            self.min_interval = response_dict.get('min interval', self.min_interval)
            self.tracker_id = response_dict.get('tracker id')
            
            self.logger.info(f"Announce successful: {len(response_dict.get('peers', []))} peers")
            return response_dict
            
        except urllib.error.URLError as e:
            raise TrackerError(f"HTTP request failed: {e}")
        except Exception as e:
            raise TrackerError(f"Announce failed: {e}")
    
    def _parse_announce_response(self, response: Dict[bytes, Any]) -> Dict[str, Any]:
        """
        Parse tracker announce response.
        
        Args:
            response: Decoded bencoded response
            
        Returns:
            Parsed response dictionary
        """
        result = {}
        
        # Basic fields
        if b'interval' in response:
            result['interval'] = response[b'interval']
        
        if b'min interval' in response:
            result['min interval'] = response[b'min interval']
        
        if b'tracker id' in response:
            result['tracker id'] = response[b'tracker id']
        
        if b'complete' in response:
            result['complete'] = response[b'complete']  # Number of seeders
        
        if b'incomplete' in response:
            result['incomplete'] = response[b'incomplete']  # Number of leechers
        
        # Parse peer list
        if b'peers' in response:
            peers_data = response[b'peers']
            if isinstance(peers_data, bytes):
                # Compact format: 6 bytes per peer (4 IP + 2 port)
                result['peers'] = self._parse_compact_peers(peers_data)
            elif isinstance(peers_data, list):
                # Dictionary format
                result['peers'] = self._parse_dict_peers(peers_data)
        
        return result
    
    def _parse_compact_peers(self, peers_data: bytes) -> List[Tuple[str, int]]:
        """
        Parse compact peer list format.
        
        Args:
            peers_data: Raw peer data (6 bytes per peer)
            
        Returns:
            List of (IP, port) tuples
        """
        peers = []
        
        for i in range(0, len(peers_data), 6):
            if i + 6 <= len(peers_data):
                # Extract IP (4 bytes) and port (2 bytes)
                ip_bytes = peers_data[i:i+4]
                port_bytes = peers_data[i+4:i+6]
                
                # Convert to IP address and port
                ip = socket.inet_ntoa(ip_bytes)
                port = struct.unpack('!H', port_bytes)[0]
                
                peers.append((ip, port))
        
        return peers
    
    def _parse_dict_peers(self, peers_data: List[Dict[bytes, Any]]) -> List[Tuple[str, int]]:
        """
        Parse dictionary peer list format.
        
        Args:
            peers_data: List of peer dictionaries
            
        Returns:
            List of (IP, port) tuples
        """
        peers = []
        
        for peer_dict in peers_data:
            if b'ip' in peer_dict and b'port' in peer_dict:
                ip = peer_dict[b'ip'].decode('utf-8', errors='replace')
                port = peer_dict[b'port']
                peers.append((ip, port))
        
        return peers
    
    def scrape(self, info_hashes: List[bytes] = None) -> Dict[bytes, Dict[str, int]]:
        """
        Scrape tracker for torrent statistics.
        
        Args:
            info_hashes: List of info hashes to scrape (defaults to current torrent)
            
        Returns:
            Dictionary mapping info hashes to statistics
            
        Raises:
            TrackerError: If scrape request fails
        """
        if info_hashes is None:
            info_hashes = [self.info_hash]
        
        # Build scrape URL
        scrape_url = self.announce_url.replace('/announce', '/scrape')
        if scrape_url == self.announce_url:
            # Fallback: try common scrape URL patterns
            if self.announce_url.endswith('/announce'):
                scrape_url = self.announce_url[:-9] + '/scrape'
            else:
                scrape_url = self.announce_url + '/scrape'
        
        # Build query parameters
        params = []
        for info_hash in info_hashes:
            params.append(('info_hash', info_hash))
        
        query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        full_url = f"{scrape_url}?{query_string}"
        
        try:
            request = urllib.request.Request(full_url)
            request.add_header('User-Agent', 'BitTorrent-CLI-Client/1.0')
            
            with urllib.request.urlopen(request, timeout=30) as response:
                response_data = response.read()
            
            # Decode response
            decoded_response = bcoding.bdecode(response_data)
            
            if b'failure reason' in decoded_response:
                reason = decoded_response[b'failure reason'].decode('utf-8', errors='replace')
                raise TrackerError(f"Scrape error: {reason}")
            
            # Parse files dictionary
            files_dict = decoded_response.get(b'files', {})
            result = {}
            
            for info_hash, stats in files_dict.items():
                result[info_hash] = {
                    'complete': stats.get(b'complete', 0),
                    'incomplete': stats.get(b'incomplete', 0),
                    'downloaded': stats.get(b'downloaded', 0)
                }
            
            return result
            
        except Exception as e:
            raise TrackerError(f"Scrape failed: {e}")


class UDPTracker:
    """
    UDP BitTorrent tracker communication.
    
    Implements the UDP tracker protocol as specified in BEP 15.
    """
    
    def __init__(self, announce_url: str, info_hash: bytes, peer_id: bytes, port: int):
        """
        Initialize UDP tracker.
        
        Args:
            announce_url: Tracker announce URL (udp://host:port/announce)
            info_hash: 20-byte SHA1 hash of torrent info dict
            peer_id: 20-byte peer ID
            port: Port number for incoming connections
        """
        self.announce_url = announce_url
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.port = port
        
        # Parse URL
        parsed = urllib.parse.urlparse(announce_url)
        self.host = parsed.hostname
        self.tracker_port = parsed.port or 80
        
        # Connection state
        self.connection_id = None
        self.connection_expires = 0
        
        # Statistics
        self.uploaded = 0
        self.downloaded = 0
        self.left = 0
        
        # Setup logging
        self.logger = logging.getLogger(f"UDPTracker({self.host}:{self.tracker_port})")
    
    def _connect(self) -> int:
        """
        Establish connection with UDP tracker.
        
        Returns:
            Connection ID for subsequent requests
            
        Raises:
            TrackerError: If connection fails
        """
        # Check if existing connection is still valid
        if self.connection_id and time.time() < self.connection_expires:
            return self.connection_id
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(15)
        
        try:
            # Connection request format:
            # Offset  Size    Name            Value
            # 0       64-bit  protocol_id     0x41727101980 (magic constant)
            # 8       32-bit  action          0 (connect)
            # 12      32-bit  transaction_id  random
            
            protocol_id = 0x41727101980
            action = 0  # Connect
            transaction_id = random.randint(0, 2**32 - 1)
            
            request = struct.pack('!QII', protocol_id, action, transaction_id)
            
            # Send request with retries
            for attempt in range(3):
                try:
                    sock.sendto(request, (self.host, self.tracker_port))
                    response, addr = sock.recvfrom(16)
                    break
                except socket.timeout:
                    if attempt == 2:
                        raise TrackerError("Connection timeout")
                    continue
            
            # Parse response
            if len(response) != 16:
                raise TrackerError(f"Invalid connection response length: {len(response)}")
            
            resp_action, resp_transaction_id, connection_id = struct.unpack('!IIQ', response)
            
            if resp_action != 0:
                raise TrackerError(f"Invalid connection response action: {resp_action}")
            
            if resp_transaction_id != transaction_id:
                raise TrackerError("Transaction ID mismatch in connection response")
            
            # Store connection info
            self.connection_id = connection_id
            self.connection_expires = time.time() + 60  # Connection valid for 1 minute
            
            self.logger.debug(f"Connected to UDP tracker: {connection_id}")
            return connection_id
            
        except socket.gaierror as e:
            raise TrackerError(f"DNS resolution failed: {e}")
        except Exception as e:
            raise TrackerError(f"Connection failed: {e}")
        finally:
            sock.close()
    
    def announce(self, event: str = None, numwant: int = 50) -> Dict[str, Any]:
        """
        Send announce request to UDP tracker.
        
        Args:
            event: Event type ('started', 'stopped', 'completed', or None)
            numwant: Number of peers requested
            
        Returns:
            Dictionary containing tracker response
            
        Raises:
            TrackerError: If announce request fails
        """
        connection_id = self._connect()
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(15)
        
        try:
            # Announce request format:
            # Offset  Size    Name            Value
            # 0       64-bit  connection_id   from connect response
            # 8       32-bit  action          1 (announce)
            # 12      32-bit  transaction_id  random
            # 16      20-byte info_hash       torrent info hash
            # 36      20-byte peer_id         client peer ID
            # 56      64-bit  downloaded      bytes downloaded
            # 64      64-bit  left            bytes left to download
            # 72      64-bit  uploaded        bytes uploaded
            # 80      32-bit  event           event type
            # 84      32-bit  IP address      0 (default)
            # 88      32-bit  key             random key
            # 92      32-bit  num_want        number of peers requested
            # 96      16-bit  port            client listening port
            
            action = 1  # Announce
            transaction_id = random.randint(0, 2**32 - 1)
            
            # Event mapping
            event_map = {
                None: 0,
                'completed': 1,
                'started': 2,
                'stopped': 3
            }
            event_value = event_map.get(event, 0)
            
            ip_address = 0  # Use default
            key = random.randint(0, 2**32 - 1)
            
            request = struct.pack('!QII20s20sQQQIIIiH',
                                connection_id, action, transaction_id,
                                self.info_hash, self.peer_id,
                                self.downloaded, self.left, self.uploaded,
                                event_value, ip_address, key, numwant, self.port)
            
            # Send request with retries
            for attempt in range(3):
                try:
                    sock.sendto(request, (self.host, self.tracker_port))
                    response, addr = sock.recvfrom(1024)
                    break
                except socket.timeout:
                    if attempt == 2:
                        raise TrackerError("Announce timeout")
                    continue
            
            # Parse response
            if len(response) < 20:
                raise TrackerError(f"Invalid announce response length: {len(response)}")
            
            # Check for error response
            resp_action = struct.unpack('!I', response[:4])[0]
            if resp_action == 3:  # Error
                if len(response) >= 8:
                    resp_transaction_id = struct.unpack('!I', response[4:8])[0]
                    if resp_transaction_id == transaction_id:
                        error_message = response[8:].decode('utf-8', errors='replace')
                        raise TrackerError(f"Tracker error: {error_message}")
                raise TrackerError("Unknown tracker error")
            
            # Parse successful announce response
            if resp_action != 1:
                raise TrackerError(f"Invalid announce response action: {resp_action}")
            
            resp_transaction_id, interval, leechers, seeders = struct.unpack('!IIII', response[4:20])
            
            if resp_transaction_id != transaction_id:
                raise TrackerError("Transaction ID mismatch in announce response")
            
            # Parse peer list
            peers_data = response[20:]
            peers = []
            
            for i in range(0, len(peers_data), 6):
                if i + 6 <= len(peers_data):
                    ip_bytes = peers_data[i:i+4]
                    port_bytes = peers_data[i+4:i+6]
                    
                    ip = socket.inet_ntoa(ip_bytes)
                    port = struct.unpack('!H', port_bytes)[0]
                    
                    # Skip invalid peers
                    try:
                        ipaddress.ip_address(ip)
                        if 1 <= port <= 65535:
                            peers.append((ip, port))
                    except ValueError:
                        continue
            
            result = {
                'interval': interval,
                'complete': seeders,
                'incomplete': leechers,
                'peers': peers
            }
            
            self.logger.info(f"Announce successful: {len(peers)} peers, "
                           f"{seeders} seeders, {leechers} leechers")
            return result
            
        except Exception as e:
            if isinstance(e, TrackerError):
                raise
            raise TrackerError(f"Announce failed: {e}")
        finally:
            sock.close()
    
    def scrape(self, info_hashes: List[bytes] = None) -> Dict[bytes, Dict[str, int]]:
        """
        Scrape UDP tracker for torrent statistics.
        
        Args:
            info_hashes: List of info hashes to scrape (defaults to current torrent)
            
        Returns:
            Dictionary mapping info hashes to statistics
            
        Raises:
            TrackerError: If scrape request fails
        """
        if info_hashes is None:
            info_hashes = [self.info_hash]
        
        if len(info_hashes) > 74:  # UDP scrape limit
            info_hashes = info_hashes[:74]
        
        connection_id = self._connect()
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(15)
        
        try:
            # Scrape request format:
            # Offset  Size    Name            Value
            # 0       64-bit  connection_id   from connect response
            # 8       32-bit  action          2 (scrape)
            # 12      32-bit  transaction_id  random
            # 16+     20-byte info_hash       repeated for each hash
            
            action = 2  # Scrape
            transaction_id = random.randint(0, 2**32 - 1)
            
            request = struct.pack('!QII', connection_id, action, transaction_id)
            for info_hash in info_hashes:
                request += info_hash
            
            # Send request
            sock.sendto(request, (self.host, self.tracker_port))
            response, addr = sock.recvfrom(1024)
            
            # Parse response
            if len(response) < 8:
                raise TrackerError(f"Invalid scrape response length: {len(response)}")
            
            resp_action, resp_transaction_id = struct.unpack('!II', response[:8])
            
            if resp_action == 3:  # Error
                error_message = response[8:].decode('utf-8', errors='replace')
                raise TrackerError(f"Scrape error: {error_message}")
            
            if resp_action != 2:
                raise TrackerError(f"Invalid scrape response action: {resp_action}")
            
            if resp_transaction_id != transaction_id:
                raise TrackerError("Transaction ID mismatch in scrape response")
            
            # Parse statistics (12 bytes per info hash)
            stats_data = response[8:]
            result = {}
            
            for i, info_hash in enumerate(info_hashes):
                offset = i * 12
                if offset + 12 <= len(stats_data):
                    complete, downloaded, incomplete = struct.unpack('!III', 
                                                                   stats_data[offset:offset+12])
                    result[info_hash] = {
                        'complete': complete,
                        'downloaded': downloaded,
                        'incomplete': incomplete
                    }
            
            return result
            
        except Exception as e:
            if isinstance(e, TrackerError):
                raise
            raise TrackerError(f"Scrape failed: {e}")
        finally:
            sock.close()


class TrackerManager:
    """
    Manages communication with multiple trackers.
    
    Handles tracker selection, failover, and announce scheduling
    according to BitTorrent protocol best practices.
    """
    
    def __init__(self, torrent, peer_id: bytes, port: int):
        """
        Initialize tracker manager.
        
        Args:
            torrent: Torrent object containing tracker URLs
            peer_id: 20-byte peer ID
            port: Port for incoming connections
        """
        self.torrent = torrent
        self.peer_id = peer_id
        self.port = port
        
        # Create tracker instances
        self.trackers = []
        self._create_trackers()
        
        # State
        self.current_tracker = None
        self.last_announce = 0
        self.interval = 1800
        self.min_interval = 900
        
        # Statistics
        self.uploaded = 0
        self.downloaded = 0
        self.left = torrent.total_length
        
        # Setup logging
        self.logger = logging.getLogger("TrackerManager")
    
    def _create_trackers(self):
        """Create tracker instances from torrent announce URLs."""
        # Add primary tracker
        if self.torrent.announce:
            tracker = self._create_tracker(self.torrent.announce)
            if tracker:
                self.trackers.append(tracker)
        
        # Add trackers from announce-list
        for tier in self.torrent.announce_list:
            tier_trackers = []
            for announce_url in tier:
                if announce_url != self.torrent.announce:  # Avoid duplicates
                    tracker = self._create_tracker(announce_url)
                    if tracker:
                        tier_trackers.append(tracker)
            if tier_trackers:
                self.trackers.extend(tier_trackers)
    
    def _create_tracker(self, announce_url: str):
        """
        Create appropriate tracker instance based on URL scheme.
        
        Args:
            announce_url: Tracker announce URL
            
        Returns:
            Tracker instance or None if unsupported
        """
        try:
            if announce_url.startswith(('http://', 'https://')):
                return HTTPTracker(announce_url, self.torrent.info_hash, 
                                 self.peer_id, self.port)
            elif announce_url.startswith('udp://'):
                return UDPTracker(announce_url, self.torrent.info_hash,
                                self.peer_id, self.port)
            else:
                self.logger.warning(f"Unsupported tracker protocol: {announce_url}")
                return None
        except Exception as e:
            self.logger.error(f"Failed to create tracker for {announce_url}: {e}")
            return None
    
    def announce(self, event: str = None, numwant: int = 50) -> List[Tuple[str, int]]:
        """
        Announce to trackers and get peer list.
        
        Args:
            event: Event type ('started', 'stopped', 'completed', or None)
            numwant: Number of peers requested
            
        Returns:
            List of (IP, port) tuples for discovered peers
        """
        all_peers = []
        successful_announces = 0
        
        # Update tracker statistics
        for tracker in self.trackers:
            tracker.uploaded = self.uploaded
            tracker.downloaded = self.downloaded
            tracker.left = self.left
        
        # Try each tracker
        for tracker in self.trackers:
            try:
                self.logger.debug(f"Announcing to {tracker.announce_url}")
                response = tracker.announce(event=event, numwant=numwant)
                
                # Collect peers
                peers = response.get('peers', [])
                all_peers.extend(peers)
                
                # Update intervals
                if 'interval' in response:
                    self.interval = max(response['interval'], self.min_interval)
                if 'min interval' in response:
                    self.min_interval = response['min interval']
                
                # Mark as current tracker if first successful
                if not self.current_tracker:
                    self.current_tracker = tracker
                
                successful_announces += 1
                
                self.logger.info(f"Tracker {tracker.announce_url}: "
                               f"{len(peers)} peers, "
                               f"{response.get('complete', 0)} seeders, "
                               f"{response.get('incomplete', 0)} leechers")
                
            except TrackerError as e:
                self.logger.warning(f"Tracker {tracker.announce_url} failed: {e}")
                continue
            except Exception as e:
                self.logger.error(f"Unexpected error with tracker {tracker.announce_url}: {e}")
                continue
        
        # Remove duplicate peers
        unique_peers = list(set(all_peers))
        
        # Update announce time
        self.last_announce = time.time()
        
        self.logger.info(f"Announce complete: {len(unique_peers)} unique peers "
                        f"from {successful_announces}/{len(self.trackers)} trackers")
        
        return unique_peers
    
    def should_announce(self) -> bool:
        """
        Check if it's time for a regular announce.
        
        Returns:
            True if announce is due
        """
        return time.time() - self.last_announce >= self.interval
    
    def update_stats(self, uploaded: int, downloaded: int, left: int):
        """
        Update transfer statistics.
        
        Args:
            uploaded: Total bytes uploaded
            downloaded: Total bytes downloaded
            left: Bytes remaining to download
        """
        self.uploaded = uploaded
        self.downloaded = downloaded
        self.left = left


if __name__ == "__main__":
    # Example usage and testing
    import sys
    from torrent_complete import Torrent
    
    if len(sys.argv) != 2:
        print("Usage: python tracker.py <torrent_file>")
        sys.exit(1)
    
    try:
        # Load torrent
        torrent = Torrent(sys.argv[1])
        
        # Create tracker manager
        peer_id = b'-PC0001-' + bytes([random.randint(0, 255) for _ in range(12)])
        tracker_manager = TrackerManager(torrent, peer_id, 6881)
        
        print(f"Testing trackers for: {torrent.name}")
        print(f"Available trackers: {len(tracker_manager.trackers)}")
        
        # Test announce
        peers = tracker_manager.announce(event='started', numwant=50)
        
        print(f"\nAnnounce Results:")
        print(f"Total peers found: {len(peers)}")
        
        if peers:
            print("Sample peers:")
            for i, (ip, port) in enumerate(peers[:10]):
                print(f"  {i+1}. {ip}:{port}")
            if len(peers) > 10:
                print(f"  ... and {len(peers) - 10} more")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
