#!/usr/bin/env python3
"""
Simple HTTP tracker server for testing BitTorrent client
"""

import socket
import struct
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time

class TrackerHandler(BaseHTTPRequestHandler):
    # Store peers per torrent
    peers = {}
    
    def do_GET(self):
        """Handle tracker announce requests."""
        if self.path.startswith('/announce'):
            self.handle_announce()
        else:
            self.send_error(404)
    
    def handle_announce(self):
        """Handle BitTorrent announce request."""
        try:
            # Parse query parameters
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            
            # Extract required parameters
            info_hash = params.get('info_hash', [None])[0]
            peer_id = params.get('peer_id', [None])[0]
            port = int(params.get('port', [0])[0])
            
            if not info_hash or not peer_id:
                self.send_error(400, "Missing required parameters")
                return
            
            # Get client IP
            client_ip = self.client_address[0]
            
            # Store peer information
            if info_hash not in self.peers:
                self.peers[info_hash] = {}
            
            self.peers[info_hash][peer_id] = {
                'ip': client_ip,
                'port': port,
                'last_seen': time.time()
            }
            
            print(f"Registered peer {peer_id} at {client_ip}:{port} for torrent {info_hash}")
            
            # Build peer list (excluding requesting peer)
            peer_list = []
            for pid, peer_info in self.peers[info_hash].items():
                if pid != peer_id:  # Don't include self
                    ip = peer_info['ip']
                    port = peer_info['port']
                    # Convert IP to 4 bytes + port to 2 bytes
                    try:
                        ip_bytes = socket.inet_aton(ip)
                        port_bytes = struct.pack('!H', port)
                        peer_list.append(ip_bytes + port_bytes)
                    except:
                        continue
            
            # Create tracker response
            response = {
                'interval': 30,  # 30 seconds between announces
                'complete': len(self.peers.get(info_hash, {})),  # Number of seeders
                'incomplete': 0,  # Number of leechers
                'peers': b''.join(peer_list)  # Compact peer list
            }
            
            # Encode response
            import bencodepy
            response_data = bencodepy.encode(response)
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', str(len(response_data)))
            self.end_headers()
            self.wfile.write(response_data)
            
            print(f"Sent {len(peer_list)} peers to {client_ip}:{port}")
            
        except Exception as e:
            print(f"Error handling announce: {e}")
            self.send_error(500, str(e))
    
    def log_message(self, format, *args):
        """Override to reduce log spam."""
        pass

def start_tracker(port=8080):
    """Start the tracker server."""
    server = HTTPServer(('', port), TrackerHandler)
    print(f"Starting tracker server on port {port}")
    print("Tracker URL: http://localhost:8080/announce")
    print("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down tracker server...")
        server.shutdown()

if __name__ == "__main__":
    start_tracker()
