# BitTorrent CLI Client

A complete BitTorrent client implementation in Python that follows the BitTorrent protocol specification. This client is modular, well-documented, and capable of downloading both single-file and multi-file torrents.

## Features

- **Full BitTorrent Protocol Support**: Implements the complete BitTorrent peer wire protocol
- **HTTP/HTTPS and UDP Tracker Support**: Compatible with both tracker types
- **Multi-file Torrent Support**: Handles both single-file and multi-file torrents
- **Resume Functionality**: Can resume interrupted downloads
- **Real-time Progress Display**: Terminal-based progress tracking with statistics
- **Modular Architecture**: Clean, extensible code structure
- **Piece Verification**: SHA1 verification of all downloaded pieces
- **Concurrent Downloads**: Multiple peer connections for faster downloads

## Requirements

- Python 3.7+
- Dependencies listed in `requirements.txt`

## Installation

1. Clone or download the project files
2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
python main_client.py example.torrent
```

### Advanced Usage

```bash
# Specify download directory
python main_client.py example.torrent -d /home/user/downloads

# Use custom port and max peers
python main_client.py example.torrent -p 6882 -m 100

# Enable verbose output
python main_client.py example.torrent -v

# All options combined
python main_client.py example.torrent -d ./downloads -p 6881 -m 50 -v
```

### Command Line Options

- `torrent_file`: Path to the .torrent file (required)
- `-d, --download-dir`: Directory to download files to (default: ./downloads)
- `-p, --port`: Port to listen on (default: 6881)
- `-m, --max-peers`: Maximum number of peer connections (default: 50)
- `-v, --verbose`: Enable verbose output and logging

## Project Structure

The client is built with a modular architecture consisting of the following components:

### Core Modules

1. **`main_client.py`** - Main entry point and client coordination
2. **`torrent_new.py`** - Torrent file parsing and metadata handling
3. **`tracker_client.py`** - HTTP/HTTPS and UDP tracker communication
4. **`peer_client.py`** - Peer wire protocol implementation
5. **`piece_manager_client.py`** - Piece downloading and verification
6. **`file_manager_client.py`** - File I/O and directory management
7. **`progress_client.py`** - Progress tracking and display

### Module Details

#### Torrent Parser (`torrent_new.py`)
- Parses .torrent files using bcoding
- Extracts metadata (name, size, piece hashes, file structure)
- Calculates info hash for tracker communication
- Supports both single-file and multi-file torrents

#### Tracker Communication (`tracker_client.py`)
- HTTP/HTTPS tracker protocol implementation
- UDP tracker protocol implementation
- Handles announce requests (started, stopped, completed)
- Multi-tracker support with fallback

#### Peer Wire Protocol (`peer_client.py`)
- Complete BitTorrent handshake implementation
- All peer wire protocol messages (choke, unchoke, interested, have, bitfield, request, piece)
- Concurrent peer connection management
- Connection state tracking and cleanup

#### Piece Management (`piece_manager_client.py`)
- Breaks pieces into 16KB blocks
- Coordinates block requests across peers
- SHA1 piece verification
- Download strategy implementation
- Request timeout and retry handling

#### File I/O Management (`file_manager_client.py`)
- Creates proper directory structure
- Maps pieces to file segments
- Handles files spanning multiple pieces
- Resume functionality through piece verification
- Efficient file handle caching

#### Progress Tracking (`progress_client.py`)
- Real-time progress bars
- Download/upload speed calculation
- ETA estimation
- Peer connection statistics
- Terminal-based display

## Example Output

```
BitTorrent CLI Client
====================
Torrent file: example.torrent
Download directory: ./downloads
Port: 6881
Max peers: 50

Progress: |████████████████████████████| 75.00% (48/64 pieces)
Size:     786,432 / 1,048,576 bytes
Speed:    ↓ 125.3 KB/s | Avg: 98.7 KB/s | ETA: 2m 15s
Peers:    8 connected | 12 max | 25 total seen
Time:     5m 32s elapsed
```

## Technical Implementation

### Protocol Compliance
- Implements BitTorrent Protocol BEP-0003
- Proper handshake with info hash verification
- Standard 16KB block size
- Complete message set support
- Tracker announce protocol compliance

### Download Strategy
- Rarest-first piece selection (simplified implementation)
- Continuing in-progress pieces prioritization
- Multiple concurrent requests per peer
- Automatic request timeout and retry

### Error Handling
- Robust network error handling
- Automatic peer reconnection
- Piece verification and re-download
- Graceful shutdown on interruption

### Performance Features
- Concurrent peer connections
- Efficient piece-to-file mapping
- Sparse file allocation
- File handle caching
- Non-blocking I/O operations

## Testing Individual Components

Each module can be tested independently:

```bash
# Test torrent parsing
python torrent_new.py example.torrent

# Test tracker communication
python tracker_client.py example.torrent

# Test peer connection
python peer_client.py <peer_ip> <peer_port> example.torrent

# Test piece management
python piece_manager_client.py example.torrent

# Test file management
python file_manager_client.py example.torrent

# Test progress display
python progress_client.py
```

## Logging

The client creates detailed logs in `bittorrent_client.log` including:
- Connection events
- Download progress
- Error conditions
- Peer interactions
- Tracker communications

Enable verbose mode (`-v`) for console output.

## Limitations and Future Improvements

### Current Limitations
- No DHT support
- No magnet link support
- Simplified piece selection strategy
- No upload bandwidth limiting
- No peer exchange (PEX) support

### Potential Improvements
- Implement DHT for trackerless torrents
- Add magnet link support
- Advanced piece selection algorithms
- Bandwidth limiting and QoS
- Web interface for remote control
- Encrypted peer connections

## Architecture Benefits

1. **Modularity**: Each component is independent and testable
2. **Extensibility**: Easy to add new features or protocols
3. **Maintainability**: Clear separation of concerns
4. **Reusability**: Components can be used in other projects
5. **Debugging**: Isolated components simplify troubleshooting

## Contributing

This implementation serves as an educational reference for the BitTorrent protocol. The modular design makes it easy to extend or modify individual components.

## License

This project is provided as-is for educational purposes. Please respect copyright laws and only download content you have permission to access.

## References

- [BitTorrent Protocol Specification (BEP-0003)](http://bittorrent.org/beps/bep_0003.html)
- [BitTorrent Enhancement Proposals](http://bittorrent.org/beps/bep_0000.html)
- [UDP Tracker Protocol](http://bittorrent.org/beps/bep_0015.html)
