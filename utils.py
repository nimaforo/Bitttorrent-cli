# utils.py: Helper functions and constants for the BitTorrent client.

from bcoding import bencode, bdecode
import hashlib
import random
import struct

# Constants for BitTorrent protocol
PROTOCOL_STR = b'BitTorrent protocol'
RESERVED = b'\x00' * 8
BLOCK_SIZE = 16384  # 16KB block size
PEER_ID_PREFIX = b'-PC0001-'  # More standard prefix (PC = Python Client)

def generate_peer_id():
    """Generate a unique peer ID."""
    import time
    # Use timestamp for more uniqueness
    timestamp = int(time.time()) % 100000
    random_chars = ''.join(str(random.randint(0, 9)) for _ in range(7))
    suffix = f"{timestamp:05d}{random_chars}".encode()
    return PEER_ID_PREFIX + suffix

def sha1_hash(data):
    """Compute SHA1 hash of data."""
    return hashlib.sha1(data).digest()

def pack_handshake(info_hash, peer_id):
    """Pack the handshake message."""
    pstrlen = len(PROTOCOL_STR)
    return struct.pack('!B', pstrlen) + PROTOCOL_STR + RESERVED + info_hash + peer_id

def unpack_handshake(data):
    """Unpack and validate handshake."""
    pstrlen = struct.unpack('!B', data[0:1])[0]
    if pstrlen != 19 or data[1:20] != PROTOCOL_STR:
        raise ValueError("Invalid protocol")
    info_hash = data[28:48]
    peer_id = data[48:68]
    return info_hash, peer_id