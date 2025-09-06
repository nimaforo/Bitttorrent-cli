import os
import json
import hashlib
import bencodepy

def sha1_hash(data):
    return hashlib.sha1(data).digest()

def hex_dump(data, prefix="", length=16):
    """Pretty print hex dump of data."""
    hex_lines = []
    hex_line = []
    ascii_line = []
    
    for i, byte in enumerate(data):
        hex_line.append(f"{byte:02x}")
        ascii_line.append(chr(byte) if 32 <= byte <= 126 else ".")
        
        if (i + 1) % length == 0:
            hex_lines.append(f"{prefix}{' '.join(hex_line)}  |{''.join(ascii_line)}|")
            hex_line = []
            ascii_line = []
            
    if hex_line:
        hex_lines.append(f"{prefix}{' '.join(hex_line).ljust(length*3)}  |{''.join(ascii_line)}|")
    
    return "\n".join(hex_lines)

def decode_bytes(value):
    """Try to decode bytes to string, or return base64 if not possible."""
    if isinstance(value, bytes):
        try:
            return value.decode('utf-8')
        except:
            return f"base64:{value.hex()}"
    elif isinstance(value, dict):
        return {decode_bytes(k): decode_bytes(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [decode_bytes(x) for x in value]
    return value

def main():
    # Read and decode the torrent file
    with open("test.torrent", "rb") as f:
        raw_data = f.read()
        print("\nRaw torrent file contents:")
        print(raw_data)
    
        data = bencodepy.decode(raw_data)
        info = data[b'info']
        pieces = info[b'pieces']
        
        # Convert to JSON-friendly format
        decoded = decode_bytes(data)
        print("\nDecoded torrent contents:")
        print(json.dumps(decoded, indent=2))
        
        # Show piece information
        print(f"\nPiece length: {info[b'piece length']} bytes")
        print(f"Total pieces: {len(pieces) // 20}")
        
        print("\nPiece hashes:")
        for i in range(0, len(pieces), 20):
            piece = pieces[i:i+20]
            print(f"Piece {i//20}: {piece.hex()}")
            
        # Show target piece and size
        print(f"\nTarget length: {info[b'length']} bytes")
    
    # Print all piece hashes
    print("\nPiece hashes:")
    for i in range(0, len(pieces), 20):
        piece_hash = pieces[i:i+20]
        print(f"Piece {i//20}: {piece_hash.hex()}")
    
    # Create test content and verify hash
    first_piece = pieces[:20]
    print(f"\nTarget hash for first piece: {first_piece.hex()}")
    
    # Try some sample content
    test_content = b"This is a test file that will have exactly 42 bytes.."
    content_hash = sha1_hash(test_content)
    print(f"\nTest content length: {len(test_content)} bytes")
    print(f"Test content hash: {content_hash.hex()}")
    print("\nTest content hex dump:")
    print(hex_dump(test_content))
    
    # If hashes don't match, save what we have for analysis
    if content_hash != first_piece:
        print("\nHashes don't match! Saving current and target content...")
        with open("downloads/test.txt", "wb") as f:
            f.write(test_content)
        print("Saved current content to downloads/test.txt")

if __name__ == "__main__":
    main()
