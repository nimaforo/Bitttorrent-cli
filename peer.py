# peer.py: Handles peer connections, handshakes, and message exchange.

import socket
import struct
import threading
from bitstring import BitArray
from utils import pack_handshake, unpack_handshake, PROTOCOL_STR, BLOCK_SIZE
from pubsub import pub

class Peer:
    def __init__(self, ip, port, torrent, peer_id, piece_manager, is_seeding=False):
        """Initialize peer connection."""
        self.ip = ip
        self.port = port
        self.torrent = torrent
        self.peer_id = peer_id
        self.piece_manager = piece_manager
        self.is_seeding = is_seeding
        self.sock = None
        self.choked = True
        self.bitfield = None
        self.closing = False
        if is_seeding:
            # Subscribe to piece requests with explicit handler
            pub.subscribe(self.on_piece_requested, 'piece_requested')

    def connect(self):
        """Connect to peer and perform handshake."""
        try:
            print(f"\nConnecting to peer {self.ip}:{self.port}")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(30)  # Increased timeout
            
            # Skip connection to self check
            if self.ip == '127.0.0.1':
                # Get our local port to avoid connecting to self
                try:
                    self.sock.bind(('', 0))
                    our_port = self.sock.getsockname()[1]
                    if our_port == self.port or 6881 <= self.port <= 6889:
                        raise Exception("Skipping connection to self")
                except:
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.sock.settimeout(30)

            print(f"Attempting TCP connection to {self.ip}:{self.port}")
            self.sock.connect((self.ip, self.port))
            
            print("Sending handshake...")
            handshake = pack_handshake(self.torrent.info_hash, self.peer_id)
            self.sock.send(handshake)
            
            print("Waiting for handshake response...")
            recv = self.sock.recv(68)
            if len(recv) != 68:
                raise Exception(f"Invalid handshake length: {len(recv)} bytes")
                
            info_hash, peer_id = unpack_handshake(recv)
            print(f"Received handshake from peer: {peer_id.hex()}")
            
            if info_hash != self.torrent.info_hash:
                raise Exception("Info hash mismatch")
                
            print("Handshake successful, setting up message handler")
            self.sock.settimeout(30)
            
            # Start message handling thread
            self.message_handler = threading.Thread(
                target=self.handle_messages,
                name=f"peer-{self.ip}:{self.port}"
            )
            self.message_handler.daemon = True
            self.message_handler.start()
            
            if not self.is_seeding:
                print("Sending interested message")
                self.send_interested()
                
            print(f"Successfully connected to peer {self.ip}:{self.port}")
            return True
            
        except Exception as e:
            print(f"Error connecting to peer {self.ip}:{self.port}: {str(e)}")
            if self.sock:
                self.sock.close()
            return False

    def handle_messages(self):
        """Handle incoming messages from peer."""
        print(f"Starting message handler for peer {self.ip}:{self.port}")
        buffer = b''
        while not self.closing:
            try:
                data = self.sock.recv(4096)
                if not data:
                    print(f"Peer {self.ip}:{self.port} disconnected cleanly")
                    break

                buffer += data
                
                # Process complete messages
                while len(buffer) >= 4:
                    # Get message length
                    if len(buffer) < 4:
                        break
                    length = struct.unpack('!I', buffer[:4])[0]
                    
                    # Check if we have the complete message
                    if len(buffer) < 4 + length:
                        break
                        
                    # Extract and process message
                    msg = buffer[4:4+length]
                    buffer = buffer[4+length:]
                    
                    # Handle keep-alive messages
                    if length == 0:
                        continue
                        
                    msg_id = msg[0]
                    payload = msg[1:]
                    self.process_message(msg_id, payload)
                    
            except socket.timeout:
                # Timeouts are normal, just continue
                continue
            except Exception as e:
                print(f"Error handling messages from {self.ip}:{self.port}: {str(e)}")
                break
                
        # Clean up
        try:
            if self.sock:
                self.sock.close()
        except:
            pass
        
        print(f"Message handler stopped for peer {self.ip}:{self.port}")

    def process_message(self, msg_id, payload):
        """Process BitTorrent message."""
        try:
            if msg_id == 0:  # choke
                print(f"Peer {self.ip}:{self.port} choked us")
                self.choked = True
            elif msg_id == 1:  # unchoke
                print(f"Peer {self.ip}:{self.port} unchoked us")
                self.choked = False
                if self.bitfield and not self.is_seeding:
                    self.request_pieces()
            elif msg_id == 5:  # bitfield
                print(f"Received bitfield from {self.ip}:{self.port}")
                self.bitfield = BitArray(bytes=payload)
                print(f"Pieces available: {self.bitfield.count(True)}")
                if not self.choked and not self.is_seeding:
                    self.request_pieces()
            elif msg_id == 7:  # piece
                if not self.is_seeding:
                    index, begin = struct.unpack('!II', payload[:8])
                    block = payload[8:]
                    print(f"Received piece {index} offset {begin} length {len(block)} from {self.ip}:{self.port}")
                    self.piece_manager.receive_block(index, begin, block)
            elif msg_id == 6:  # request (for seeding)
                if self.is_seeding:
                    index, begin, length = struct.unpack('!III', payload)
                    print(f"Received request for piece {index} offset {begin} length {length} from {self.ip}:{self.port}")
                    pub.sendMessage('piece_requested', index=index, begin=begin, length=length, peer=self)
            elif msg_id == 2:  # interested
                if self.is_seeding:
                    print(f"Peer {self.ip}:{self.port} is interested")
                    self.send_unchoke()
        except Exception as e:
            print(f"Error processing message type {msg_id} from {self.ip}:{self.port}: {str(e)}")

    def send_message(self, msg_id, payload=b''):
        """Send a message to peer."""
        try:
            length = len(payload) + 1
            msg = struct.pack('!IB', length, msg_id) + payload
            self.sock.send(msg)
            print(f"Sent message type {msg_id} to peer {self.ip}:{self.port}")
        except Exception as e:
            print(f"Error sending message to {self.ip}:{self.port}: {str(e)}")
            raise

    def send_interested(self):
        """Send interested message."""
        print(f"Sending interested to {self.ip}:{self.port}")
        self.send_message(2)

    def send_unchoke(self):
        """Send unchoke message."""
        print(f"Sending unchoke to {self.ip}:{self.port}")
        self.send_message(1)
        self.choked = False

    def send_bitfield(self, bitfield):
        """Send bitfield message."""
        print(f"Sending bitfield to {self.ip}:{self.port}")
        self.send_message(5, bitfield.tobytes())

    def send_piece(self, index, begin, block):
        """Send piece message."""
        print(f"Sending piece {index} offset {begin} length {len(block)} to {self.ip}:{self.port}")
        header = struct.pack('!II', index, begin)
        self.send_message(7, header + block)

    def request_pieces(self):
        """Request pieces from peer if available."""
        print(f"Looking for pieces to request from {self.ip}:{self.port}")
        print("Checking which pieces to request...")
        requests_made = 0
        for index in range(self.torrent.num_pieces):
            if self.piece_manager.has_piece(index):
                print(f"Skip piece {index} - already have it")
                continue
            
            if index < len(self.bitfield) and self.bitfield[index]:
                print(f"Found needed piece {index} at {self.ip}:{self.port}")
                piece_len = self.piece_length(index)
                num_blocks = (piece_len + BLOCK_SIZE - 1) // BLOCK_SIZE
                
                print(f"Requesting {num_blocks} blocks for piece {index}")
                for b in range(num_blocks):
                    begin = b * BLOCK_SIZE
                    length = min(BLOCK_SIZE, piece_len - begin)
                    self.send_request(index, begin, length)
                    requests_made += 1
                
        if requests_made == 0:
            print("No new pieces to request from this peer")

    def piece_length(self, index):
        """Get length of a piece."""
        if index == self.torrent.num_pieces - 1:
            return self.torrent.total_length - index * self.torrent.piece_length
        return self.torrent.piece_length

    def handle_incoming(self, conn):
        """Handle incoming connection for seeding."""
        try:
            self.sock = conn
            peer_info = conn.getpeername()
            print(f"\nHandling incoming connection from {peer_info[0]}:{peer_info[1]}")
            
            # Perform handshake
            self.sock.settimeout(10)  # Short timeout for handshake
            recv = self.sock.recv(68)
            if len(recv) != 68:
                raise Exception(f"Invalid handshake length: {len(recv)} bytes")
            
            info_hash, remote_peer_id = unpack_handshake(recv)
            print(f"Received handshake with info_hash={info_hash.hex()} from peer={remote_peer_id.hex()}")
            
            if info_hash != self.torrent.info_hash:
                raise Exception("Info hash mismatch")
            
            # Send handshake response
            print("Sending handshake response...")
            handshake = pack_handshake(self.torrent.info_hash, self.peer_id)
            self.sock.send(handshake)
            print("Handshake complete")
            
            # Send our bitfield
            print("Sending initial bitfield...")
            bitfield = self.piece_manager.get_bitfield()
            self.send_bitfield(bitfield)
            print("Bitfield sent")
            
            # Start message handling thread
            print(f"Starting message handler for incoming peer {peer_info[0]}:{peer_info[1]}")
            self.message_handler = threading.Thread(
                target=self.handle_messages,
                name=f"peer-incoming-{peer_info[0]}:{peer_info[1]}"
            )
            self.message_handler.daemon = True
            self.message_handler.start()
            
        except socket.timeout:
            print("Connection timed out during handshake")
            if self.sock:
                self.sock.close()
        except Exception as e:
            print(f"Error handling incoming peer: {str(e)}")
            if self.sock:
                self.sock.close()
            raise
            self.sock.close()

    def send_request(self, index, begin, length):
        """Send piece request message."""
        print(f"Requesting piece {index} offset {begin} length {length} from {self.ip}:{self.port}")
        header = struct.pack('!III', index, begin, length)
        self.send_message(6, header)

    def close(self):
        """Close the peer connection."""
        self.closing = True
        if self.sock:
            try:
                self.sock.close()
            except:
                pass