"""
DHT (Distributed Hash Table) implementation for BitTorrent peer discovery.
This enables finding peers without relying on trackers.
"""

import socket
import struct
import random
import time
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
import bencodepy

class DHTNode:
    """DHT Node for BitTorrent peer discovery."""
    
    def __init__(self, port=6881):
        self.port = port
        self.node_id = self._generate_node_id()
        self.bootstrap_nodes = [
            ('router.bittorrent.com', 6881),
            ('dht.transmissionbt.com', 6881),
            ('router.utorrent.com', 6881),
            ('dht.aelitis.com', 6881),
            ('dht.libtorrent.org', 25401)
        ]
        self.routing_table = {}
        self.socket = None
        
    def _generate_node_id(self):
        """Generate a random 20-byte node ID."""
        return hashlib.sha1(str(random.random()).encode()).digest()
    
    def start(self):
        """Start DHT node."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(5)
            print(f"✓ DHT node started on port {self.port}")
            return True
        except Exception as e:
            print(f"✗ Failed to start DHT node: {e}")
            return False
    
    def stop(self):
        """Stop DHT node."""
        if self.socket:
            self.socket.close()
            self.socket = None
    
    def find_peers(self, info_hash, max_peers=50):
        """Find peers for a torrent using DHT."""
        print("🌐 Searching DHT network for peers...")
        
        if not self.socket:
            if not self.start():
                return []
        
        peers = []
        
        # Bootstrap with known nodes
        self._bootstrap()
        
        # Try to find peers
        peers.extend(self._get_peers(info_hash, max_peers))
        
        if peers:
            print(f"✓ DHT found {len(peers)} peers")
        else:
            print("✗ No peers found via DHT")
            
        return peers
    
    def _bootstrap(self):
        """Bootstrap DHT by connecting to known nodes."""
        print("🔄 Bootstrapping DHT network...")
        
        for host, port in self.bootstrap_nodes:
            try:
                # Send ping to bootstrap node
                transaction_id = self._generate_transaction_id()
                ping_msg = {
                    b't': transaction_id,
                    b'y': b'q',
                    b'q': b'ping',
                    b'a': {b'id': self.node_id}
                }
                
                data = bencodepy.encode(ping_msg)
                self.socket.sendto(data, (host, port))
                
                # Try to receive response
                try:
                    response, addr = self.socket.recvfrom(1024)
                    # Node responded, add to routing table
                    self.routing_table[addr] = time.time()
                    print(f"✓ Connected to DHT node: {host}:{port}")
                except socket.timeout:
                    pass
                    
            except Exception as e:
                print(f"✗ Failed to connect to {host}:{port}: {e}")
                continue
    
    def _get_peers(self, info_hash, max_peers):
        """Get peers for specific info_hash."""
        peers = []
        
        # Convert info_hash to bytes if needed
        if isinstance(info_hash, str):
            info_hash = info_hash.encode('latin1')
        
        # Try each known node
        for addr in list(self.routing_table.keys()):
            try:
                transaction_id = self._generate_transaction_id()
                get_peers_msg = {
                    b't': transaction_id,
                    b'y': b'q',
                    b'q': b'get_peers',
                    b'a': {
                        b'id': self.node_id,
                        b'info_hash': info_hash
                    }
                }
                
                data = bencodepy.encode(get_peers_msg)
                self.socket.sendto(data, addr)
                
                # Wait for response
                try:
                    response, response_addr = self.socket.recvfrom(1024)
                    response_data = bencodepy.decode(response)
                    
                    if b'r' in response_data and b'values' in response_data[b'r']:
                        # Found peers!
                        peer_data = response_data[b'r'][b'values']
                        for peer_bytes in peer_data:
                            if len(peer_bytes) == 6:  # IPv4 address + port
                                ip = socket.inet_ntoa(peer_bytes[:4])
                                port = struct.unpack('!H', peer_bytes[4:6])[0]
                                peers.append((ip, port))
                                
                                if len(peers) >= max_peers:
                                    break
                    
                    # Also collect nodes for future queries
                    if b'r' in response_data and b'nodes' in response_data[b'r']:
                        nodes_data = response_data[b'r'][b'nodes']
                        self._parse_nodes(nodes_data)
                        
                except socket.timeout:
                    pass
                except Exception as e:
                    print(f"DHT query error: {e}")
                    
            except Exception as e:
                continue
                
        return peers
    
    def _parse_nodes(self, nodes_data):
        """Parse compact node info from DHT response."""
        try:
            # Each node is 26 bytes: 20 byte ID + 4 byte IP + 2 byte port
            for i in range(0, len(nodes_data), 26):
                if i + 26 <= len(nodes_data):
                    node_data = nodes_data[i:i+26]
                    node_id = node_data[:20]
                    ip = socket.inet_ntoa(node_data[20:24])
                    port = struct.unpack('!H', node_data[24:26])[0]
                    
                    # Add to routing table
                    self.routing_table[(ip, port)] = time.time()
        except Exception as e:
            pass
    
    def _generate_transaction_id(self):
        """Generate a random transaction ID."""
        return bytes([random.randint(0, 255) for _ in range(2)])

def find_dht_peers(info_hash, port=6881, max_peers=50):
    """Standalone function to find peers via DHT."""
    dht = DHTNode(port)
    try:
        return dht.find_peers(info_hash, max_peers)
    finally:
        dht.stop()
