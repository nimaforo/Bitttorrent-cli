from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import bencodepy
import threading
import time
import sys

class TrackerHandler(BaseHTTPRequestHandler):
    peers = {}  # info_hash -> set of (ip, port) tuples
    
    def log_request(self, code='-', size='-'):
        """Log an accepted request."""
        print(f"{self.client_address[0]} - - [{time.strftime('%d/%b/%Y %H:%M:%S')}] "
              f"\"{self.requestline}\" {code} {size}")
    
    def do_GET(self):
        # Parse query parameters
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        print(f"\nTracker request from {self.client_address[0]}: {self.path}")
        
        # Extract info_hash and peer info
        if b'info_hash' in params:
            info_hash = params[b'info_hash'][0]
            peer_id = params[b'peer_id'][0] if b'peer_id' in params else None
            port = int(params[b'port'][0]) if b'port' in params else None
            print(f"Got announce from peer {peer_id.hex() if peer_id else 'unknown'} "
                  f"on port {port} for torrent {info_hash.hex()}")
            
            if info_hash not in self.peers:
                self.peers[info_hash] = set()
                print(f"New torrent registered: {info_hash.hex()}")
                
            # Add this peer to the list
            peer_addr = (self.client_address[0], port)
            self.peers[info_hash].add(peer_addr)
            print(f"Added peer {self.client_address[0]}:{port} to torrent {info_hash.hex()}")
            
            # Prepare response with peer list
            peer_list = []
            for peer_addr in self.peers[info_hash]:
                addr, p = peer_addr  # Correctly unpack the tuple
                if (addr, p) != (self.client_address[0], port):  # Don't send peer its own address
                    peer_list.append({b'ip': addr.encode('utf-8'), b'port': p})
                    peer_list.append({b'ip': addr.encode('utf-8'), b'port': p})
            
            # Create response dictionary
            response = {
                b'interval': 1800,
                b'peers': peer_list
            }
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(bencodepy.encode(response))
        else:
            self.send_response(400)
            self.end_headers()
            
def run_tracker(port=6969):
    try:
        server = HTTPServer(('', port), TrackerHandler)  # Listen on all interfaces
        print(f"Starting tracker on port {port}")
        print("Press Ctrl+C to stop")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down tracker...")
        server.server_close()
    except Exception as e:
        print(f"Error starting tracker: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    run_tracker()
