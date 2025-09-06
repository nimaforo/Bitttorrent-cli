# magnet.py: Handles magnet link parsing and DHT-based peer discovery

import socket
import struct
import random
import hashlib
from urllib.parse import parse_qs, urlparse
import binascii

def parse_magnet(magnet_uri):
    """Parse a magnet URI into its components."""
    if not magnet_uri.startswith('magnet:?'):
        raise ValueError("Not a valid magnet URI")
        
    # Parse the URI
    params = parse_qs(magnet_uri[8:])
    
    result = {
        'xt': [],      # Exact Topic (urn:btih:info_hash)
        'dn': None,    # Display Name
        'tr': [],      # Tracker URLs
        'nodes': [],   # DHT nodes
        'xl': None,    # Exact Length
        'kt': [],      # Keyword Topic
        'mt': [],      # Manifest Topic
        'ut': [],      # URL Topic
    }
    
    # Process each parameter
    for key, values in params.items():
        if key == 'xt':
            for v in values:
                if v.startswith('urn:btih:'):
                    # Convert hex hash to bytes
                    hex_hash = v[9:]
                    if len(hex_hash) == 32:  # Base32 encoded
                        info_hash = base32_decode(hex_hash)
                    else:  # Hex encoded
                        info_hash = bytes.fromhex(hex_hash)
                    result['xt'].append(info_hash)
        elif key == 'dn':
            result['dn'] = values[0]
        elif key == 'tr':
            result['tr'].extend(values)
        elif key == 'xl':
            result['xl'] = int(values[0])
            
    return result

def create_magnet(info_hash, name=None, trackers=None, nodes=None):
    """Create a magnet link from components."""
    if isinstance(info_hash, bytes):
        info_hash = binascii.hexlify(info_hash).decode()
        
    magnet = f"magnet:?xt=urn:btih:{info_hash}"
    
    if name:
        from urllib.parse import quote
        magnet += f"&dn={quote(name)}"
        
    if trackers:
        for tracker in trackers:
            magnet += f"&tr={quote(tracker)}"
            
    if nodes:
        for node in nodes:
            magnet += f"&dht={quote(node)}"
            
    return magnet

def base32_decode(s):
    """Decode base32 string to bytes."""
    s = s.upper()
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    bits = ""
    
    # Convert base32 chars to bits
    for c in s:
        if c not in alphabet:
            raise ValueError(f"Invalid base32 character: {c}")
        val = alphabet.index(c)
        bits += format(val, '05b')
        
    # Convert bits to bytes
    result = bytearray()
    for i in range(0, len(bits), 8):
        if i + 8 <= len(bits):
            result.append(int(bits[i:i+8], 2))
            
    return bytes(result)
