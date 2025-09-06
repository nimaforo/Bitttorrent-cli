#!/usr/bin/env python3
"""
Start a seeder for the test torrent
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from client import Client

def start_seeder():
    """Start seeding the test torrent."""
    torrent_path = "test.torrent"
    output_dir = "."  # Current directory has the file
    
    if not os.path.exists(torrent_path):
        print(f"Error: {torrent_path} not found")
        return
    
    if not os.path.exists("test_data.txt"):
        print("Error: test_data.txt not found")
        return
    
    print("Starting seeder for test.torrent")
    client = Client(torrent_path, output_dir, seed=True)
    
    # Use a different port for the seeder
    client.port = 6882
    client.tracker.port = 6882  # Make sure tracker uses the same port
    
    try:
        client.start()
    except KeyboardInterrupt:
        print("\nStopping seeder...")
        client.stop()

if __name__ == "__main__":
    start_seeder()
