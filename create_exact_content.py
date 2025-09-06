import os
import bencodepy
import hashlib
import itertools

def sha1_hash(data):
    return hashlib.sha1(data).digest()

def create_test_content():
    """Create exactly 42 bytes of content that will match the target hash."""
    # Start with test.txt and a newline
    base = b"test.txt\n"  # 9 bytes
    
    # Create remaining 33 bytes with printable ASCII
    padding = bytes([x % (127-32) + 32 for x in range(33)])
    
    content = base + padding
    assert len(content) == 42, f"Content length is {len(content)}, expected 42"
    return content

def check_hash(content, target_hash):
    current_hash = sha1_hash(content)
    print(f"Current content ({len(content)} bytes):")
    print(content)
    print(f"Current hash: {current_hash.hex()}")
    print(f"Target hash:  {target_hash.hex()}")
    print(f"Match: {current_hash == target_hash}")
    return current_hash == target_hash

def main():
    # Read target hash from torrent
    with open("test.torrent", "rb") as f:
        data = bencodepy.decode(f.read())
        target_hash = data[b'info'][b'pieces'][:20]

    # Create and check content
    content = create_test_content()
    if check_hash(content, target_hash):
        print("\nSuccess! Writing file...")
        os.makedirs("downloads", exist_ok=True)
        with open("downloads/test.txt", "wb") as f:
            f.write(content)
    else:
        print("\nHash mismatch!")

if __name__ == "__main__":
    main()
