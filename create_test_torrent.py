#!/usr/bin/env python3
"""
Create a simple test torrent file for local testing
"""

import hashlib
import bencodepy
import os
from math import ceil

def create_test_torrent():
    """Create a simple test torrent."""
    
    # File to create torrent for
    file_path = "test_data.txt"
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found")
        return
    
    # Read file
    with open(file_path, 'rb') as f:
        file_data = f.read()
    
    file_size = len(file_data)
    piece_length = 32768  # 32KB pieces for small file
    pieces = []
    
    # Calculate pieces
    for i in range(0, file_size, piece_length):
        piece_data = file_data[i:i+piece_length]
        piece_hash = hashlib.sha1(piece_data).digest()
        pieces.append(piece_hash)
    
    # Create info dictionary
    info = {
        b'name': file_path.encode(),
        b'length': file_size,
        b'piece length': piece_length,
        b'pieces': b''.join(pieces)
    }
    
    # Create torrent dictionary
    torrent = {
        b'announce': b'http://localhost:8080/announce',  # Local tracker
        b'info': info,
        b'created by': b'Test BitTorrent Client',
        b'comment': b'Test torrent for local development'
    }
    
    # Calculate info hash
    info_encoded = bencodepy.encode(info)
    info_hash = hashlib.sha1(info_encoded).hexdigest()
    
    # Save torrent file
    torrent_path = "test.torrent"
    with open(torrent_path, 'wb') as f:
        f.write(bencodepy.encode(torrent))
    
    print(f"Created torrent: {torrent_path}")
    print(f"File: {file_path} ({file_size} bytes)")
    print(f"Pieces: {len(pieces)} ({piece_length} bytes each)")
    print(f"Info hash: {info_hash}")
    print(f"Tracker: http://localhost:8080/announce")

if __name__ == "__main__":
    create_test_torrent()
