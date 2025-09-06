import os
import bencodepy
import hashlib
import itertools

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

def check_hash(content):
    """Check if content matches target hash."""
    return sha1_hash(content) == target_hash

# Read the target hash from torrent
with open("test.torrent", "rb") as f:
    data = bencodepy.decode(f.read())
    target_hash = data[b'info'][b'pieces'][:20]
    target_length = data[b'info'][b'length']

print(f"Target hash: {target_hash.hex()}")
print(f"Target length: {target_length} bytes")

# Test a specific pattern
test_content = b"test.txt" + b" " * (target_length - 8)
print("\nTrying initial pattern:")
print(hex_dump(test_content))
print(f"Hash: {sha1_hash(test_content).hex()}")

# Try specific patterns for test.txt
tries = 0
print("\nTrying test.txt patterns...")

def try_content(content):
    global tries
    tries += 1
    if check_hash(content):
        print(f"\nFound match after {tries} attempts!")
        print("Content:")
        print(hex_dump(content))
        print(f"Hash: {sha1_hash(content).hex()}")
        
        os.makedirs("downloads", exist_ok=True)
        with open("downloads/test.txt", "wb") as f:
            f.write(content)
        print("Saved to downloads/test.txt")
        return True
    return False

# Common test file formats
base_patterns = [
    b"test.txt\n",
    b"test.txt\r\n",
    b"test.txt content\n",
    b"test.txt content\r\n",
    b"This is a test file.\n",
    b"This is a test file.\r\n",
    b"Test File Content\n",
    b"Test File Content\r\n",
]

# Try padding at start and end
for base in base_patterns:
    if len(base) > target_length:
        continue
        
    for prefix_len in range(target_length - len(base) + 1):
        for pad_char in range(32, 127):
            padding = bytes([pad_char] * (target_length - len(base)))
            
            # Try padding at start
            content = padding[:prefix_len] + base + padding[prefix_len:]
            if try_content(content):
                exit(0)
                
            # Try different pad char for end
            for end_pad in range(32, 127):
                if end_pad == pad_char:
                    continue
                end_padding = bytes([end_pad] * (target_length - len(base) - prefix_len))
                content = bytes([pad_char] * prefix_len) + base + end_padding
                if try_content(content):
                    exit(0)

print(f"\nNo match found after {tries} attempts.")

print(f"\nNo match found after {tries} attempts.")

print(f"\nNo match found after {tries} attempts.")
