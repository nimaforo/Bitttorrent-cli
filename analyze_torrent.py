import bencodepy
import hashlib
from collections import OrderedDict

def decode_torrent(path):
    with open(path, "rb") as f:
        return bencodepy.decode(f.read())

def extract_info_dict(torrent_data):
    return torrent_data.get(b'info', {})

def analyze_info_dict(info_dict):
    print("\nTorrent Info Analysis:")
    for key, value in info_dict.items():
        if key == b'pieces':
            print(f"pieces (first piece hash): {value[:20].hex()}")
            if len(value) > 20:
                print(f"Number of pieces: {len(value) // 20}")
        elif isinstance(value, (bytes, bytearray)):
            try:
                str_val = value.decode('utf-8')
                print(f"{key.decode('utf-8')}: {str_val}")
            except UnicodeDecodeError:
                print(f"{key.decode('utf-8')}: {value.hex()}")
        elif isinstance(value, (dict, OrderedDict)):
            print(f"\n{key.decode('utf-8')}:")
            for k, v in value.items():
                if isinstance(v, (bytes, bytearray)):
                    try:
                        str_val = v.decode('utf-8')
                        print(f"  {k.decode('utf-8')}: {str_val}")
                    except UnicodeDecodeError:
                        print(f"  {k.decode('utf-8')}: {v.hex()}")
                else:
                    print(f"  {k.decode('utf-8')}: {v}")
        else:
            print(f"{key.decode('utf-8')}: {value}")

def compute_info_hash(info_dict):
    print("\nInfo Hash Analysis:")
    encoded = bencodepy.encode(info_dict)
    info_hash = hashlib.sha1(encoded).hexdigest()
    print(f"Info Hash: {info_hash}")
    print(f"Info Dictionary size: {len(encoded)} bytes")
    print("\nInfo Dictionary Hex Dump:")
    for i in range(0, len(encoded), 32):
        chunk = encoded[i:i+32]
        hex_str = ' '.join(f"{b:02x}" for b in chunk)
        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
        print(f"{i:04x}: {hex_str:<48} | {ascii_str}")

if __name__ == "__main__":
    torrent_path = "test.torrent"
    print(f"Analyzing torrent: {torrent_path}")
    
    # Load and analyze torrent
    torrent_data = decode_torrent(torrent_path)
    info_dict = extract_info_dict(torrent_data)
    
    # Print analysis
    analyze_info_dict(info_dict)
    compute_info_hash(info_dict)
