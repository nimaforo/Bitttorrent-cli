"""
BitTorrent Peer Wire Protocol Implementation

This module handles the BitTorrent peer wire protocol for communication
between peers according to the BitTorrent protocol specification (BEP 3).
It manages peer connections, handshakes, and message exchange.

Author: BitTorrent CLI Client
"""

import socket
import struct
import threading
import time
import logging
from typing import Optional, Callable, Set
from bitstring import BitArray


class PeerMessage:
    """BitTorrent peer wire protocol message types."""
    CHOKE = 0
    UNCHOKE = 1
    INTERESTED = 2
    NOT_INTERESTED = 3
    HAVE = 4
    BITFIELD = 5
    REQUEST = 6
    PIECE = 7
    CANCEL = 8
    PORT = 9  # DHT port message


class PeerError(Exception):
    """Exception raised for peer-related errors."""
    pass


class Peer:
    """
    BitTorrent peer connection and communication.
    
    Implements the peer wire protocol for downloading pieces from
    and uploading pieces to other BitTorrent clients.
    """
    
    BLOCK_SIZE = 16384  # 16KB block size (standard)
    HANDSHAKE_TIMEOUT = 30
    MESSAGE_TIMEOUT = 60
    KEEP_ALIVE_INTERVAL = 120
    
    def __init__(self, ip: str, port: int, info_hash: bytes, peer_id: bytes,
                 piece_manager, file_manager):
        """
        Initialize peer connection.
        
        Args:
            ip: Peer IP address
            port: Peer port number
            info_hash: 20-byte SHA1 hash of torrent info dict
            peer_id: Our 20-byte peer ID
            piece_manager: PieceManager instance for piece coordination
            file_manager: FileManager instance for file I/O
        """
        self.ip = ip
        self.port = port
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.piece_manager = piece_manager
        self.file_manager = file_manager
        
        # Connection state
        self.socket = None
        self.connected = False
        self.handshake_complete = False
        
        # Peer state
        self.peer_id_remote = None
        self.am_choking = True
        self.am_interested = False
        self.peer_choking = True
        self.peer_interested = False
        
        # Piece availability
        self.bitfield = None
        self.have_pieces: Set[int] = set()
        
        # Request management
        self.pending_requests = {}  # (piece_index, block_offset) -> timestamp
        self.max_pending_requests = 10
        
        # Threading
        self.running = False
        self.message_thread = None
        self.keep_alive_thread = None
        
        # Statistics
        self.bytes_downloaded = 0
        self.bytes_uploaded = 0
        self.connect_time = 0
        self.last_message_time = 0
        
        # Callbacks
        self.on_piece_received: Optional[Callable] = None
        self.on_disconnect: Optional[Callable] = None
        
        # Setup logging
        self.logger = logging.getLogger(f"Peer({ip}:{port})")
    
    def connect(self) -> bool:
        """
        Connect to the peer and perform handshake.
        
        Returns:
            True if connection and handshake successful
        """
        try:
            self.logger.debug("Attempting connection")
            
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.HANDSHAKE_TIMEOUT)
            
            # Connect
            self.socket.connect((self.ip, self.port))
            self.connected = True
            self.connect_time = time.time()
            
            self.logger.debug("Socket connected, performing handshake")
            
            # Perform handshake
            if not self._perform_handshake():
                self.disconnect()
                return False
            
            # Start message handling
            self.running = True
            self.socket.settimeout(self.MESSAGE_TIMEOUT)
            
            self.message_thread = threading.Thread(target=self._message_loop, daemon=True)
            self.message_thread.start()
            
            self.keep_alive_thread = threading.Thread(target=self._keep_alive_loop, daemon=True)
            self.keep_alive_thread.start()
            
            self.logger.info("Connection established successfully")
            return True
            
        except Exception as e:
            self.logger.warning(f"Connection failed: {e}")
            self.disconnect()
            return False
    
    def disconnect(self):
        """Disconnect from peer and cleanup resources."""
        if not self.connected:
            return
        
        self.logger.debug("Disconnecting")
        
        self.running = False
        self.connected = False
        
        # Close socket
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        # Wait for threads to finish
        if self.message_thread and self.message_thread.is_alive():
            self.message_thread.join(timeout=1.0)
        
        if self.keep_alive_thread and self.keep_alive_thread.is_alive():
            self.keep_alive_thread.join(timeout=1.0)
        
        # Cancel pending requests
        for (piece_index, block_offset) in self.pending_requests:
            self.piece_manager.cancel_request(piece_index, block_offset)
        self.pending_requests.clear()
        
        # Call disconnect callback
        if self.on_disconnect:
            try:
                self.on_disconnect(self)
            except:
                pass
        
        self.logger.info("Disconnected")
    
    def _perform_handshake(self) -> bool:
        """
        Perform BitTorrent handshake.
        
        Returns:
            True if handshake successful
        """
        try:
            # Send handshake
            # Format: <pstrlen><pstr><reserved><info_hash><peer_id>
            pstr = b"BitTorrent protocol"
            pstrlen = len(pstr)
            reserved = b'\x00' * 8
            
            handshake = struct.pack('!B', pstrlen) + pstr + reserved + self.info_hash + self.peer_id
            
            self.socket.send(handshake)
            self.logger.debug("Handshake sent")
            
            # Receive handshake response
            response = self._receive_exact(68)  # Handshake is always 68 bytes
            
            if len(response) != 68:
                raise PeerError(f"Invalid handshake length: {len(response)}")
            
            # Parse response
            resp_pstrlen = response[0]
            if resp_pstrlen != 19:
                raise PeerError(f"Invalid protocol string length: {resp_pstrlen}")
            
            resp_pstr = response[1:20]
            if resp_pstr != pstr:
                raise PeerError(f"Invalid protocol string: {resp_pstr}")
            
            resp_reserved = response[20:28]
            resp_info_hash = response[28:48]
            resp_peer_id = response[48:68]
            
            # Verify info hash
            if resp_info_hash != self.info_hash:
                raise PeerError("Info hash mismatch")
            
            self.peer_id_remote = resp_peer_id
            self.handshake_complete = True
            
            self.logger.debug(f"Handshake completed with peer ID: {resp_peer_id.hex()[:16]}...")
            return True
            
        except Exception as e:
            self.logger.warning(f"Handshake failed: {e}")
            return False
    
    def _receive_exact(self, length: int) -> bytes:
        """
        Receive exactly the specified number of bytes.
        
        Args:
            length: Number of bytes to receive
            
        Returns:
            Received bytes
            
        Raises:
            PeerError: If connection is closed or timeout occurs
        """
        data = b''
        while len(data) < length:
            try:
                chunk = self.socket.recv(length - len(data))
                if not chunk:
                    raise PeerError("Connection closed by peer")
                data += chunk
            except socket.timeout:
                raise PeerError("Receive timeout")
            except Exception as e:
                raise PeerError(f"Receive error: {e}")
        
        return data
    
    def _message_loop(self):
        """Main message handling loop."""
        self.logger.debug("Message loop started")
        
        while self.running and self.connected:
            try:
                # Receive message length (4 bytes)
                length_data = self._receive_exact(4)
                message_length = struct.unpack('!I', length_data)[0]
                
                # Handle keep-alive message (length = 0)
                if message_length == 0:
                    self.last_message_time = time.time()
                    continue
                
                # Receive message payload
                message_data = self._receive_exact(message_length)
                self.last_message_time = time.time()
                
                # Process message
                self._handle_message(message_data)
                
            except PeerError as e:
                self.logger.debug(f"Message loop error: {e}")
                break
            except Exception as e:
                self.logger.warning(f"Unexpected message loop error: {e}")
                break
        
        self.logger.debug("Message loop ended")
        self.disconnect()
    
    def _handle_message(self, message_data: bytes):
        """
        Handle incoming peer message.
        
        Args:
            message_data: Raw message data (without length prefix)
        """
        if len(message_data) == 0:
            return  # Keep-alive
        
        message_id = message_data[0]
        payload = message_data[1:]
        
        if message_id == PeerMessage.CHOKE:
            self._handle_choke()
        elif message_id == PeerMessage.UNCHOKE:
            self._handle_unchoke()
        elif message_id == PeerMessage.INTERESTED:
            self._handle_interested()
        elif message_id == PeerMessage.NOT_INTERESTED:
            self._handle_not_interested()
        elif message_id == PeerMessage.HAVE:
            self._handle_have(payload)
        elif message_id == PeerMessage.BITFIELD:
            self._handle_bitfield(payload)
        elif message_id == PeerMessage.REQUEST:
            self._handle_request(payload)
        elif message_id == PeerMessage.PIECE:
            self._handle_piece(payload)
        elif message_id == PeerMessage.CANCEL:
            self._handle_cancel(payload)
        elif message_id == PeerMessage.PORT:
            self._handle_port(payload)
        else:
            self.logger.warning(f"Unknown message ID: {message_id}")
    
    def _handle_choke(self):
        """Handle choke message."""
        self.peer_choking = True
        self.logger.debug("Peer choked us")
        
        # Cancel all pending requests
        for (piece_index, block_offset) in list(self.pending_requests.keys()):
            self.piece_manager.cancel_request(piece_index, block_offset)
        self.pending_requests.clear()
    
    def _handle_unchoke(self):
        """Handle unchoke message."""
        self.peer_choking = False
        self.logger.debug("Peer unchoked us")
        
        # Request pieces if we're interested
        if self.am_interested:
            self._request_pieces()
    
    def _handle_interested(self):
        """Handle interested message."""
        self.peer_interested = True
        self.logger.debug("Peer is interested")
        
        # Unchoke peer if we have pieces they want
        if self.am_choking and self._should_unchoke_peer():
            self.send_unchoke()
    
    def _handle_not_interested(self):
        """Handle not interested message."""
        self.peer_interested = False
        self.logger.debug("Peer is not interested")
    
    def _handle_have(self, payload: bytes):
        """Handle have message."""
        if len(payload) != 4:
            self.logger.warning(f"Invalid have message length: {len(payload)}")
            return
        
        piece_index = struct.unpack('!I', payload)[0]
        self.have_pieces.add(piece_index)
        
        # Update bitfield if we have one
        if self.bitfield and piece_index < len(self.bitfield):
            self.bitfield[piece_index] = True
        
        self.logger.debug(f"Peer has piece {piece_index}")
        
        # Send interested if we need this piece
        if not self.am_interested and self.piece_manager.need_piece(piece_index):
            self.send_interested()
    
    def _handle_bitfield(self, payload: bytes):
        """Handle bitfield message."""
        try:
            self.bitfield = BitArray(bytes=payload)
            
            # Update have_pieces set
            self.have_pieces.clear()
            for i in range(len(self.bitfield)):
                if self.bitfield[i]:
                    self.have_pieces.add(i)
            
            self.logger.debug(f"Received bitfield: {len(self.have_pieces)} pieces")
            
            # Send interested if peer has pieces we need
            if not self.am_interested and self._peer_has_needed_pieces():
                self.send_interested()
                
        except Exception as e:
            self.logger.warning(f"Failed to parse bitfield: {e}")
    
    def _handle_request(self, payload: bytes):
        """Handle request message."""
        if len(payload) != 12:
            self.logger.warning(f"Invalid request message length: {len(payload)}")
            return
        
        piece_index, block_offset, block_length = struct.unpack('!III', payload)
        
        self.logger.debug(f"Peer requested piece {piece_index}, offset {block_offset}, length {block_length}")
        
        # Only send if we're not choking and have the piece
        if not self.am_choking and self.piece_manager.have_piece(piece_index):
            self._send_piece_block(piece_index, block_offset, block_length)
    
    def _handle_piece(self, payload: bytes):
        """Handle piece message."""
        if len(payload) < 8:
            self.logger.warning(f"Invalid piece message length: {len(payload)}")
            return
        
        piece_index, block_offset = struct.unpack('!II', payload[:8])
        block_data = payload[8:]
        
        self.logger.debug(f"Received block: piece {piece_index}, offset {block_offset}, length {len(block_data)}")
        
        # Remove from pending requests
        request_key = (piece_index, block_offset)
        if request_key in self.pending_requests:
            del self.pending_requests[request_key]
        
        # Update statistics
        self.bytes_downloaded += len(block_data)
        
        # Pass to piece manager
        if self.piece_manager.add_block(piece_index, block_offset, block_data):
            # Piece completed
            if self.on_piece_received:
                try:
                    self.on_piece_received(piece_index)
                except:
                    pass
        
        # Request more pieces
        self._request_pieces()
    
    def _handle_cancel(self, payload: bytes):
        """Handle cancel message."""
        if len(payload) != 12:
            self.logger.warning(f"Invalid cancel message length: {len(payload)}")
            return
        
        piece_index, block_offset, block_length = struct.unpack('!III', payload)
        self.logger.debug(f"Peer cancelled request: piece {piece_index}, offset {block_offset}")
    
    def _handle_port(self, payload: bytes):
        """Handle DHT port message."""
        if len(payload) != 2:
            self.logger.warning(f"Invalid port message length: {len(payload)}")
            return
        
        dht_port = struct.unpack('!H', payload)[0]
        self.logger.debug(f"Peer DHT port: {dht_port}")
    
    def _keep_alive_loop(self):
        """Send periodic keep-alive messages."""
        while self.running and self.connected:
            try:
                time.sleep(self.KEEP_ALIVE_INTERVAL)
                
                if self.running and self.connected:
                    self._send_keep_alive()
                    
            except Exception as e:
                self.logger.debug(f"Keep-alive error: {e}")
                break
    
    def _send_message(self, message_id: Optional[int], payload: bytes = b''):
        """
        Send a message to the peer.
        
        Args:
            message_id: Message type ID (None for keep-alive)
            payload: Message payload
        """
        if not self.connected:
            return
        
        try:
            if message_id is None:
                # Keep-alive message (length = 0)
                message = struct.pack('!I', 0)
            else:
                # Regular message
                message_data = struct.pack('!B', message_id) + payload
                message = struct.pack('!I', len(message_data)) + message_data
            
            self.socket.send(message)
            
        except Exception as e:
            self.logger.debug(f"Send error: {e}")
            self.disconnect()
    
    def _send_keep_alive(self):
        """Send keep-alive message."""
        self._send_message(None)
    
    def send_choke(self):
        """Send choke message."""
        self.am_choking = True
        self._send_message(PeerMessage.CHOKE)
        self.logger.debug("Sent choke")
    
    def send_unchoke(self):
        """Send unchoke message."""
        self.am_choking = False
        self._send_message(PeerMessage.UNCHOKE)
        self.logger.debug("Sent unchoke")
    
    def send_interested(self):
        """Send interested message."""
        self.am_interested = True
        self._send_message(PeerMessage.INTERESTED)
        self.logger.debug("Sent interested")
        
        # Request pieces if not choked
        if not self.peer_choking:
            self._request_pieces()
    
    def send_not_interested(self):
        """Send not interested message."""
        self.am_interested = False
        self._send_message(PeerMessage.NOT_INTERESTED)
        self.logger.debug("Sent not interested")
    
    def send_have(self, piece_index: int):
        """Send have message."""
        payload = struct.pack('!I', piece_index)
        self._send_message(PeerMessage.HAVE, payload)
        self.logger.debug(f"Sent have for piece {piece_index}")
    
    def send_bitfield(self, bitfield: BitArray):
        """Send bitfield message."""
        payload = bitfield.bytes
        self._send_message(PeerMessage.BITFIELD, payload)
        self.logger.debug(f"Sent bitfield")
    
    def _request_pieces(self):
        """Request pieces from peer."""
        if not self.am_interested or self.peer_choking:
            return
        
        # Limit number of pending requests
        while len(self.pending_requests) < self.max_pending_requests:
            # Find a block to request
            request = self.piece_manager.get_next_request(self.have_pieces)
            if not request:
                break
            
            piece_index, block_offset, block_length = request
            
            # Send request
            payload = struct.pack('!III', piece_index, block_offset, block_length)
            self._send_message(PeerMessage.REQUEST, payload)
            
            # Track request
            self.pending_requests[(piece_index, block_offset)] = time.time()
            
            self.logger.debug(f"Requested piece {piece_index}, offset {block_offset}, length {block_length}")
    
    def _send_piece_block(self, piece_index: int, block_offset: int, block_length: int):
        """Send a piece block to the peer."""
        try:
            # Get block data from file manager
            block_data = self.file_manager.read_block(piece_index, block_offset, block_length)
            
            if block_data:
                payload = struct.pack('!II', piece_index, block_offset) + block_data
                self._send_message(PeerMessage.PIECE, payload)
                
                # Update statistics
                self.bytes_uploaded += len(block_data)
                
                self.logger.debug(f"Sent piece {piece_index}, offset {block_offset}, length {len(block_data)}")
            
        except Exception as e:
            self.logger.warning(f"Failed to send piece block: {e}")
    
    def _peer_has_needed_pieces(self) -> bool:
        """Check if peer has pieces we need."""
        for piece_index in self.have_pieces:
            if self.piece_manager.need_piece(piece_index):
                return True
        return False
    
    def _should_unchoke_peer(self) -> bool:
        """Determine if we should unchoke this peer."""
        # Simple algorithm: unchoke if peer is interested
        # More sophisticated algorithms could consider upload rates, etc.
        return self.peer_interested
    
    def cancel_pending_requests(self):
        """Cancel all pending piece requests."""
        for (piece_index, block_offset) in list(self.pending_requests.keys()):
            payload = struct.pack('!III', piece_index, block_offset, self.BLOCK_SIZE)
            self._send_message(PeerMessage.CANCEL, payload)
            
            self.piece_manager.cancel_request(piece_index, block_offset)
        
        self.pending_requests.clear()
        self.logger.debug("Cancelled all pending requests")
    
    def cleanup_stale_requests(self, timeout: int = 60):
        """Remove requests that have been pending too long."""
        current_time = time.time()
        stale_requests = []
        
        for (piece_index, block_offset), request_time in self.pending_requests.items():
            if current_time - request_time > timeout:
                stale_requests.append((piece_index, block_offset))
        
        for piece_index, block_offset in stale_requests:
            del self.pending_requests[(piece_index, block_offset)]
            self.piece_manager.cancel_request(piece_index, block_offset)
        
        if stale_requests:
            self.logger.debug(f"Cleaned up {len(stale_requests)} stale requests")
    
    @property
    def download_rate(self) -> float:
        """Get current download rate in bytes per second."""
        if self.connect_time == 0:
            return 0.0
        
        elapsed = time.time() - self.connect_time
        return self.bytes_downloaded / elapsed if elapsed > 0 else 0.0
    
    @property
    def upload_rate(self) -> float:
        """Get current upload rate in bytes per second."""
        if self.connect_time == 0:
            return 0.0
        
        elapsed = time.time() - self.connect_time
        return self.bytes_uploaded / elapsed if elapsed > 0 else 0.0
    
    def __str__(self) -> str:
        """String representation of peer."""
        status = []
        if self.connected:
            status.append("connected")
        if self.am_interested:
            status.append("interested")
        if not self.peer_choking:
            status.append("unchoked")
        
        return (f"Peer({self.ip}:{self.port}, "
                f"pieces={len(self.have_pieces)}, "
                f"status={','.join(status) if status else 'idle'})")
    
    def __repr__(self) -> str:
        """Detailed string representation."""
        return self.__str__()


class PeerManager:
    """
    Manages multiple peer connections for BitTorrent client.
    
    Coordinates peer discovery, connection management, and
    data transfer across multiple peers.
    """
    
    def __init__(self, torrent, piece_manager, listen_port: int = 6881, max_peers: int = 50):
        """
        Initialize peer manager.
        
        Args:
            torrent: Torrent object
            piece_manager: PieceManager instance
            listen_port: Port to listen for incoming connections
            max_peers: Maximum number of concurrent peer connections
        """
        self.torrent = torrent
        self.piece_manager = piece_manager
        self.listen_port = listen_port
        self.max_peers = max_peers
        
        # Peer tracking
        self.connected_peers = {}  # peer_id -> Peer object
        self.peer_addresses = set()  # Track unique (ip, port) combinations
        self.total_peers_seen = 0
        
        # Threading
        self.running = False
        self.peer_threads = []
        self.lock = threading.RLock()
        
        # Statistics
        self.total_downloaded = 0
        self.total_uploaded = 0
        
        # Setup logging
        self.logger = logging.getLogger("PeerManager")
    
    def start(self):
        """Start the peer manager."""
        self.running = True
        self.logger.info(f"PeerManager started (max_peers: {self.max_peers})")
    
    def stop(self):
        """Stop the peer manager and disconnect all peers."""
        self.running = False
        
        # Disconnect all peers
        with self.lock:
            for peer in list(self.connected_peers.values()):
                peer.disconnect()
            
            self.connected_peers.clear()
        
        # Wait for peer threads to finish
        for thread in self.peer_threads:
            if thread.is_alive():
                thread.join(timeout=5.0)
        
        self.logger.info("PeerManager stopped")
    
    def add_peer(self, ip: str, port: int, peer_id: bytes = None) -> bool:
        """
        Add a peer for connection.
        
        Args:
            ip: Peer IP address
            port: Peer port
            peer_id: Optional peer ID
            
        Returns:
            True if peer was added, False if rejected
        """
        # Check if we already have this peer
        peer_addr = (ip, port)
        if peer_addr in self.peer_addresses:
            return False
        
        # Check peer limit
        with self.lock:
            if len(self.connected_peers) >= self.max_peers:
                return False
        
        # Create and start peer connection
        try:
            peer = Peer(ip, port, self.torrent, self.piece_manager)
            
            # Start connection in separate thread
            thread = threading.Thread(
                target=self._handle_peer_connection,
                args=(peer,),
                daemon=True
            )
            thread.start()
            self.peer_threads.append(thread)
            
            self.peer_addresses.add(peer_addr)
            self.total_peers_seen += 1
            
            self.logger.debug(f"Added peer {ip}:{port}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add peer {ip}:{port}: {e}")
            return False
    
    def _handle_peer_connection(self, peer):
        """Handle a peer connection in a separate thread."""
        try:
            # Connect to peer
            if peer.connect():
                with self.lock:
                    peer_id = f"{peer.ip}:{peer.port}"
                    self.connected_peers[peer_id] = peer
                
                self.logger.info(f"Connected to peer {peer.ip}:{peer.port}")
                
                # Let peer handle communication
                peer.run()
                
            else:
                self.logger.debug(f"Failed to connect to peer {peer.ip}:{peer.port}")
                
        except Exception as e:
            self.logger.error(f"Peer connection error {peer.ip}:{peer.port}: {e}")
        
        finally:
            # Clean up
            with self.lock:
                peer_id = f"{peer.ip}:{peer.port}"
                if peer_id in self.connected_peers:
                    del self.connected_peers[peer_id]
            
            peer_addr = (peer.ip, peer.port)
            if peer_addr in self.peer_addresses:
                self.peer_addresses.remove(peer_addr)
            
            # Update statistics
            self.total_downloaded += peer.bytes_downloaded
            self.total_uploaded += peer.bytes_uploaded
    
    def get_peer_stats(self) -> dict:
        """
        Get peer statistics.
        
        Returns:
            Dictionary with peer statistics
        """
        with self.lock:
            return {
                'connected_peers': len(self.connected_peers),
                'total_peers_seen': self.total_peers_seen,
                'max_peers': self.max_peers,
                'total_downloaded': self.total_downloaded,
                'total_uploaded': self.total_uploaded
            }
    
    def disconnect_slow_peers(self, min_rate: float = 1024):
        """
        Disconnect peers with low download rates.
        
        Args:
            min_rate: Minimum acceptable download rate in bytes/sec
        """
        slow_peers = []
        
        with self.lock:
            for peer_id, peer in self.connected_peers.items():
                if peer.download_rate < min_rate and peer.bytes_downloaded > 0:
                    slow_peers.append(peer_id)
        
        for peer_id in slow_peers:
            peer = self.connected_peers.get(peer_id)
            if peer:
                self.logger.info(f"Disconnecting slow peer {peer.ip}:{peer.port} "
                               f"(rate: {peer.download_rate:.1f} B/s)")
                peer.disconnect()


if __name__ == "__main__":
    # Example usage and testing
    print("BitTorrent Peer Wire Protocol Implementation")
    print("This module is designed to be used as part of a BitTorrent client.")
    print("Run the main client to see peers in action.")
