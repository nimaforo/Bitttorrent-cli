import os
import hashlib
import bencodepy
import itertools
import string

def sha1_hash(data):
    return hashlib.sha1(data).digest()

# Read the target hash from torrent
with open("test.torrent", "rb") as f:
    data = bencodepy.decode(f.read())
    target_hash = data[b'info'][b'pieces'][:20]

print(f"Target hash: {target_hash.hex()}")

# Create a file with fixed size of 42 bytes
def try_content(prefix, suffix, padding_char):
    content = prefix
    padding_len = 42 - len(prefix) - len(suffix)
    if padding_len >= 0:
        content += bytes([padding_char] * padding_len) + suffix
        if len(content) == 42:
            return content
    return None

# Try some variations
bases = [
    b"test",
    b"Test",
    b"test file",
    b"Test file",
    b"test.txt",
    b"Test.txt",
    b"test file 42",
    b"Test file 42",
]

suffixes = [
    b".",
    b"!",
    b"",
]

# Try all printable ASCII characters for padding
for prefix in prefixes:
    for suffix in suffixes:
        for padding_char in range(32, 127):  # printable ASCII
            content = try_content(prefix, suffix, padding_char)
            if content is None:
                continue
                
            content_hash = sha1_hash(content)
            if content_hash == target_hash:
                print("\nFound matching content!")
                print(f"Content ({len(content)} bytes): {content}")
                print(f"Content as string: {content.decode('ascii')}")
                print(f"Hash: {content_hash.hex()}")
                
                # Save the content
                with open("downloads/test.txt", "wb") as f:
                    f.write(content)
                print("\nSaved matching content to downloads/test.txt")
