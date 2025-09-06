#!/usr/bin/env python3
"""
BitTorrent Peer Wire Protocol Implementation

This module handles peer connections and implements the BitTorrent peer wire protocol
for communicating with other peers in the swarm.
"""

import socket
import struct
import threading
import time
import logging
from typing import Optional, Callable, Set, List, Tuple, Dict
from enum import Enum
import bitstring


class PeerMessage(Enum):
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
    PORT = 9  # DHT extension


class PeerState:
    """Represents the state of a peer connection."""
    
    def __init__(self):
        self.am_choking = True
        self.am_interested = False
        self.peer_choking = True
        self.peer_interested = False
        self.peer_bitfield = None
        self.pieces_available = set()
        self.pending_requests = set()  # Set of (piece_index, block_offset, block_length)
        self.last_message_time = time.time()


class PeerConnection:
    """Represents a connection to a single peer."""
    
    HANDSHAKE_LENGTH = 68
    PROTOCOL_STRING = b'BitTorrent protocol'
    BLOCK_SIZE = 16384  # 16KB standard block size
    
    def __init__(self, peer_ip: str, peer_port: int, info_hash: bytes, 
                 peer_id: bytes, num_pieces: int, message_handler: Optional[Callable] = None):
        """
        Initialize peer connection.
        
        Args:
            peer_ip: Peer IP address
            peer_port: Peer port
            info_hash: Torrent info hash
            peer_id: Our peer ID
            num_pieces: Total number of pieces in torrent
            message_handler: Callback for handling received messages
        """
        self.peer_ip = peer_ip
        self.peer_port = peer_port
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.num_pieces = num_pieces
        self.message_handler = message_handler
        
        self.socket = None
        self.state = PeerState()
        self.connected = False
        self.running = False
        self.receive_thread = None
        
        self.logger = logging.getLogger(f"{__name__}.{peer_ip}:{peer_port}")
        
        # Statistics
        self.bytes_downloaded = 0
        self.bytes_uploaded = 0
        self.connection_time = None
    
    def connect(self, timeout: int = 30) -> bool:
        """
        Connect to the peer and perform handshake.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)
            
            self.logger.debug(f"Connecting to {self.peer_ip}:{self.peer_port}")
            self.socket.connect((self.peer_ip, self.peer_port))
            
            # Perform handshake
            if not self._perform_handshake():
                self.disconnect()
                return False
            
            self.connected = True
            self.connection_time = time.time()
            self.state.last_message_time = time.time()
            
            # Start receiving messages
            self.running = True
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            
            self.logger.info(f"Connected to peer {self.peer_ip}:{self.peer_port}")
            return True
            
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            self.disconnect()
            return False
    
    def _perform_handshake(self) -> bool:
        """Perform BitTorrent handshake with peer."""
        try:
            # Send handshake
            # Format: <pstrlen><pstr><reserved><info_hash><peer_id>
            handshake = struct.pack('>B', len(self.PROTOCOL_STRING))
            handshake += self.PROTOCOL_STRING
            handshake += b'\x00' * 8  # Reserved bytes
            handshake += self.info_hash
            handshake += self.peer_id
            
            self.socket.send(handshake)
            
            # Receive handshake response
            response = self._receive_exact(self.HANDSHAKE_LENGTH)
            if not response:
                self.logger.error("Failed to receive handshake response")
                return False
            
            # Parse handshake response
            pstrlen = response[0]
            if pstrlen != len(self.PROTOCOL_STRING):
                self.logger.error(f"Invalid protocol string length: {pstrlen}")
                return False
            
            pstr = response[1:1+pstrlen]
            if pstr != self.PROTOCOL_STRING:
                self.logger.error(f"Invalid protocol string: {pstr}")
                return False
            
            reserved = response[1+pstrlen:1+pstrlen+8]
            peer_info_hash = response[1+pstrlen+8:1+pstrlen+8+20]
            peer_peer_id = response[1+pstrlen+8+20:1+pstrlen+8+20+20]
            
            if peer_info_hash != self.info_hash:
                self.logger.error("Info hash mismatch in handshake")
                return False
            
            self.logger.debug("Handshake successful")
            return True
            
        except Exception as e:
            self.logger.error(f"Handshake failed: {e}")
            return False
    
    def _receive_exact(self, length: int) -> Optional[bytes]:
        """Receive exactly the specified number of bytes."""
        data = b''
        while len(data) < length:
            try:
                chunk = self.socket.recv(length - len(data))
                if not chunk:
                    return None
                data += chunk
            except Exception:
                return None
        return data
    
    def _receive_loop(self):
        """Main loop for receiving messages from peer."""
        while self.running and self.connected:
            try:
                # Read message length (4 bytes)
                length_data = self._receive_exact(4)
                if not length_data:
                    break
                
                message_length = struct.unpack('>I', length_data)[0]
                
                if message_length == 0:
                    # Keep-alive message
                    self.state.last_message_time = time.time()
                    continue
                
                # Read message data
                message_data = self._receive_exact(message_length)
                if not message_data:
                    break
                
                self._handle_message(message_data)
                self.state.last_message_time = time.time()
                
            except Exception as e:
                self.logger.error(f"Error in receive loop: {e}")
                break
        
        self.disconnect()
    
    def _handle_message(self, message_data: bytes):
        """Handle received peer message."""
        if len(message_data) == 0:
            return
        
        message_id = message_data[0]
        payload = message_data[1:]
        
        try:
            if message_id == PeerMessage.CHOKE.value:
                self.state.peer_choking = True
                self.logger.debug("Received CHOKE")
                
            elif message_id == PeerMessage.UNCHOKE.value:
                self.state.peer_choking = False
                self.logger.debug("Received UNCHOKE")
                
            elif message_id == PeerMessage.INTERESTED.value:
                self.state.peer_interested = True
                self.logger.debug("Received INTERESTED")
                
            elif message_id == PeerMessage.NOT_INTERESTED.value:
                self.state.peer_interested = False
                self.logger.debug("Received NOT_INTERESTED")
                
            elif message_id == PeerMessage.HAVE.value:
                if len(payload) == 4:
                    piece_index = struct.unpack('>I', payload)[0]
                    self.state.pieces_available.add(piece_index)
                    self.logger.debug(f"Received HAVE for piece {piece_index}")
                
            elif message_id == PeerMessage.BITFIELD.value:
                self._handle_bitfield(payload)
                
            elif message_id == PeerMessage.REQUEST.value:
                if len(payload) == 12:
                    piece_index, block_offset, block_length = struct.unpack('>III', payload)
                    self.logger.debug(f"Received REQUEST for piece {piece_index}, offset {block_offset}, length {block_length}")
                
            elif message_id == PeerMessage.PIECE.value:
                if len(payload) >= 8:
                    piece_index, block_offset = struct.unpack('>II', payload[:8])
                    block_data = payload[8:]
                    self._handle_piece(piece_index, block_offset, block_data)
                
            elif message_id == PeerMessage.CANCEL.value:
                if len(payload) == 12:
                    piece_index, block_offset, block_length = struct.unpack('>III', payload)
                    request = (piece_index, block_offset, block_length)
                    self.state.pending_requests.discard(request)
                    self.logger.debug(f"Received CANCEL for piece {piece_index}, offset {block_offset}")
            
            # Call external message handler if provided
            if self.message_handler:
                self.message_handler(self, message_id, payload)
                
        except Exception as e:
            self.logger.error(f"Error handling message {message_id}: {e}")
    
    def _handle_bitfield(self, bitfield_data: bytes):
        """Handle bitfield message."""
        try:
            bitfield = bitstring.BitArray(bytes=bitfield_data)
            
            # Extract available pieces
            for piece_index in range(min(len(bitfield), self.num_pieces)):
                if bitfield[piece_index]:
                    self.state.pieces_available.add(piece_index)
            
            self.logger.debug(f"Received BITFIELD with {len(self.state.pieces_available)} pieces")
            
        except Exception as e:
            self.logger.error(f"Error parsing bitfield: {e}")
    
    def _handle_piece(self, piece_index: int, block_offset: int, block_data: bytes):
        """Handle piece message."""
        self.bytes_downloaded += len(block_data)
        request = (piece_index, block_offset, len(block_data))
        self.state.pending_requests.discard(request)
        
        self.logger.debug(f"Received PIECE {piece_index}, offset {block_offset}, length {len(block_data)}")
        
        # Call external message handler for piece data
        if self.message_handler:
            self.message_handler(self, PeerMessage.PIECE.value, (piece_index, block_offset, block_data))
    
    def send_message(self, message_id: int, payload: bytes = b'') -> bool:
        """Send a message to the peer."""
        if not self.connected:
            return False
        
        try:
            message_length = len(payload) + 1  # +1 for message ID
            message = struct.pack('>I', message_length) + struct.pack('>B', message_id) + payload
            self.socket.send(message)
            return True
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            self.disconnect()
            return False
    
    def send_keep_alive(self) -> bool:
        """Send keep-alive message."""
        if not self.connected:
            return False
        
        try:
            self.socket.send(struct.pack('>I', 0))
            return True
        except Exception as e:
            self.logger.error(f"Failed to send keep-alive: {e}")
            self.disconnect()
            return False
    
    def send_choke(self) -> bool:
        """Send choke message."""
        self.state.am_choking = True
        return self.send_message(PeerMessage.CHOKE.value)
    
    def send_unchoke(self) -> bool:
        """Send unchoke message."""
        self.state.am_choking = False
        return self.send_message(PeerMessage.UNCHOKE.value)
    
    def send_interested(self) -> bool:
        """Send interested message."""
        self.state.am_interested = True
        return self.send_message(PeerMessage.INTERESTED.value)
    
    def send_not_interested(self) -> bool:
        """Send not interested message."""
        self.state.am_interested = False
        return self.send_message(PeerMessage.NOT_INTERESTED.value)
    
    def send_have(self, piece_index: int) -> bool:
        """Send have message for a piece."""
        payload = struct.pack('>I', piece_index)
        return self.send_message(PeerMessage.HAVE.value, payload)
    
    def send_bitfield(self, bitfield: bitstring.BitArray) -> bool:
        """Send bitfield message."""
        payload = bitfield.tobytes()
        return self.send_message(PeerMessage.BITFIELD.value, payload)
    
    def send_request(self, piece_index: int, block_offset: int, block_length: int) -> bool:
        """Send request message for a block."""
        payload = struct.pack('>III', piece_index, block_offset, block_length)
        if self.send_message(PeerMessage.REQUEST.value, payload):
            self.state.pending_requests.add((piece_index, block_offset, block_length))
            return True
        return False
    
    def send_piece(self, piece_index: int, block_offset: int, block_data: bytes) -> bool:
        """Send piece message."""
        payload = struct.pack('>II', piece_index, block_offset) + block_data
        if self.send_message(PeerMessage.PIECE.value, payload):
            self.bytes_uploaded += len(block_data)
            return True
        return False
    
    def send_cancel(self, piece_index: int, block_offset: int, block_length: int) -> bool:
        """Send cancel message."""
        payload = struct.pack('>III', piece_index, block_offset, block_length)
        if self.send_message(PeerMessage.CANCEL.value, payload):
            self.state.pending_requests.discard((piece_index, block_offset, block_length))
            return True
        return False
    
    def has_piece(self, piece_index: int) -> bool:
        """Check if peer has a specific piece."""
        return piece_index in self.state.pieces_available
    
    def can_request(self) -> bool:
        """Check if we can request data from this peer."""
        return (self.connected and 
                not self.state.peer_choking and 
                self.state.am_interested and
                len(self.state.pending_requests) < 10)  # Limit concurrent requests
    
    def get_download_speed(self) -> float:
        """Get download speed in bytes per second."""
        if not self.connection_time:
            return 0.0
        
        elapsed = time.time() - self.connection_time
        if elapsed == 0:
            return 0.0
        
        return self.bytes_downloaded / elapsed
    
    def get_upload_speed(self) -> float:
        """Get upload speed in bytes per second."""
        if not self.connection_time:
            return 0.0
        
        elapsed = time.time() - self.connection_time
        if elapsed == 0:
            return 0.0
        
        return self.bytes_uploaded / elapsed
    
    def is_alive(self, timeout: int = 120) -> bool:
        """Check if connection is alive (received message recently)."""
        return (self.connected and 
                time.time() - self.state.last_message_time < timeout)
    
    def disconnect(self):
        """Disconnect from peer."""
        self.running = False
        self.connected = False
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1)
        
        self.logger.debug("Disconnected from peer")
    
    def __str__(self) -> str:
        """String representation of peer connection."""
        status = "Connected" if self.connected else "Disconnected"
        return (f"Peer {self.peer_ip}:{self.peer_port} - {status} - "
                f"Pieces: {len(self.state.pieces_available)} - "
                f"↓ {self.bytes_downloaded:,} ↑ {self.bytes_uploaded:,}")


class PeerManager:
    """Manages multiple peer connections."""
    
    def __init__(self, info_hash: bytes, peer_id: bytes, num_pieces: int, max_peers: int = 50):
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.num_pieces = num_pieces
        self.max_peers = max_peers
        
        self.peers = {}  # {(ip, port): PeerConnection}
        self.logger = logging.getLogger(__name__)
        
        # Statistics
        self.total_downloaded = 0
        self.total_uploaded = 0
    
    def add_peer(self, peer_ip: str, peer_port: int, message_handler: Optional[Callable] = None) -> bool:
        """Add a new peer connection."""
        if len(self.peers) >= self.max_peers:
            self.logger.debug(f"Max peers reached ({self.max_peers}), not adding {peer_ip}:{peer_port}")
            return False
        
        peer_key = (peer_ip, peer_port)
        if peer_key in self.peers:
            self.logger.debug(f"Peer {peer_ip}:{peer_port} already exists")
            return False
        
        peer = PeerConnection(peer_ip, peer_port, self.info_hash, self.peer_id, 
                            self.num_pieces, message_handler)
        
        if peer.connect():
            self.peers[peer_key] = peer
            self.logger.info(f"Added peer {peer_ip}:{peer_port}")
            return True
        else:
            self.logger.warning(f"Failed to connect to peer {peer_ip}:{peer_port}")
            return False
    
    def remove_peer(self, peer_ip: str, peer_port: int):
        """Remove a peer connection."""
        peer_key = (peer_ip, peer_port)
        if peer_key in self.peers:
            self.peers[peer_key].disconnect()
            del self.peers[peer_key]
            self.logger.info(f"Removed peer {peer_ip}:{peer_port}")
    
    def get_active_peers(self) -> List[PeerConnection]:
        """Get list of active peer connections."""
        return [peer for peer in self.peers.values() if peer.connected]
    
    def get_peers_with_piece(self, piece_index: int) -> List[PeerConnection]:
        """Get peers that have a specific piece."""
        return [peer for peer in self.get_active_peers() if peer.has_piece(piece_index)]
    
    def cleanup_dead_peers(self):
        """Remove dead peer connections."""
        dead_peers = []
        for (ip, port), peer in self.peers.items():
            if not peer.is_alive():
                dead_peers.append((ip, port))
        
        for ip, port in dead_peers:
            self.remove_peer(ip, port)
    
    def get_statistics(self) -> Dict:
        """Get peer manager statistics."""
        active_peers = self.get_active_peers()
        
        total_downloaded = sum(peer.bytes_downloaded for peer in active_peers)
        total_uploaded = sum(peer.bytes_uploaded for peer in active_peers)
        
        download_speed = sum(peer.get_download_speed() for peer in active_peers)
        upload_speed = sum(peer.get_upload_speed() for peer in active_peers)
        
        return {
            'total_peers': len(self.peers),
            'active_peers': len(active_peers),
            'total_downloaded': total_downloaded,
            'total_uploaded': total_uploaded,
            'download_speed': download_speed,
            'upload_speed': upload_speed
        }
    
    def disconnect_all(self):
        """Disconnect all peers."""
        for peer in self.peers.values():
            peer.disconnect()
        self.peers.clear()
        self.logger.info("Disconnected all peers")


if __name__ == "__main__":
    # Test peer connection functionality
    import sys
    import random
    
    if len(sys.argv) != 4:
        print("Usage: python peer_client.py <peer_ip> <peer_port> <torrent_file>")
        sys.exit(1)
    
    logging.basicConfig(level=logging.DEBUG)
    
    from torrent_new import parse_torrent
    
    try:
        peer_ip = sys.argv[1]
        peer_port = int(sys.argv[2])
        torrent = parse_torrent(sys.argv[3])
        
        peer_id = b'-PC0001-' + bytes([random.randint(0, 255) for _ in range(12)])
        
        def message_handler(peer, message_id, payload):
            print(f"Received message {message_id} from {peer.peer_ip}:{peer.peer_port}")
        
        peer = PeerConnection(peer_ip, peer_port, torrent.info_hash, peer_id, 
                            torrent.num_pieces, message_handler)
        
        if peer.connect():
            print(f"Connected to {peer_ip}:{peer_port}")
            
            # Send interested message
            peer.send_interested()
            
            # Keep connection alive for a while
            time.sleep(10)
            
            peer.disconnect()
        else:
            print(f"Failed to connect to {peer_ip}:{peer_port}")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
