# Complete BitTorrent Client Implementation

A modular, production-ready BitTorrent client implementation in Python that follows the BitTorrent protocol specification (BEP 3) with support for HTTP/HTTPS/UDP trackers and both single-file and multi-file torrents.

## Features

- **Full BitTorrent Protocol Support**: Implements BEP 3 (BitTorrent Protocol) and BEP 15 (UDP Tracker Protocol)
- **Multi-Tracker Support**: HTTP, HTTPS, and UDP trackers with automatic fallback
- **Peer Wire Protocol**: Complete peer communication with handshake, messaging, and data transfer
- **Piece Management**: Efficient piece downloading with verification and rarest-first strategy
- **File Management**: Support for both single-file and multi-file torrents
- **Progress Tracking**: Real-time progress display with download statistics
- **Modular Architecture**: Clean separation of concerns for maintainability
- **Threading**: Non-blocking operations with proper concurrency handling
- **Error Handling**: Comprehensive error handling and recovery mechanisms
- **Logging**: Detailed logging for debugging and monitoring

## Project Structure

```
BitTorrent-Client/
├── main_complete.py              # Main CLI client coordinator
├── torrent_complete.py           # Torrent file parsing and info hash calculation
├── tracker_complete.py           # HTTP/UDP tracker communication
├── peer_complete.py              # Peer wire protocol implementation
├── piece_manager_complete.py     # Piece downloading and verification
├── file_manager_complete.py      # File I/O operations and mapping
├── progress_complete.py          # Progress tracking and display
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

## Installation

1. **Clone or download the project files**

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

Required packages:
- `bcoding==1.5` - Bencoding/decoding for .torrent files
- `bitstring==3.1.7` - Bit manipulation for peer protocol
- `PyPubSub==4.0.3` - Event messaging system
- `requests>=2.24.0` - HTTP requests for trackers
- `pubsub==0.1.2` - Additional pub-sub functionality
- `ipaddress==1.0.23` - IP address validation

## Usage

### Basic Usage

```bash
python main_complete.py <torrent_file>
```

### Advanced Usage

```bash
python main_complete.py ubuntu.torrent --download-dir ./downloads --max-peers 100 --port 6882 --log-level DEBUG
```

### Command Line Options

```
positional arguments:
  torrent_file          Path to the .torrent file to download

optional arguments:
  -h, --help            Show help message and exit
  --download-dir DIR, -d DIR
                        Directory to save downloaded files (default: downloads)
  --max-peers N, -p N   Maximum number of peer connections (default: 50)
  --port PORT           Local port for peer connections (default: 6881)
  --log-level LEVEL, -l LEVEL
                        Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO)
  --log-file FILE       Log to file instead of stdout
  --quiet, -q           Suppress progress output
```

### Examples

**Download Ubuntu ISO**:
```bash
python main_complete.py ubuntu.torrent
```

**Download with custom settings**:
```bash
python main_complete.py movie.torrent --download-dir /path/to/downloads --max-peers 80 --port 6882
```

**Debug mode with file logging**:
```bash
python main_complete.py file.torrent --log-level DEBUG --log-file download.log
```

## Module Documentation

### 1. main_complete.py
**Purpose**: Main CLI client that coordinates all components
- Argument parsing and configuration
- Signal handling for graceful shutdown
- Component initialization and lifecycle management
- Main download coordination loop

### 2. torrent_complete.py
**Purpose**: Torrent file parsing and metadata handling
- Bencoding/decoding of .torrent files
- Info hash calculation for tracker communication
- Support for single-file and multi-file torrents
- File structure analysis and validation

### 3. tracker_complete.py
**Purpose**: Tracker communication (HTTP/HTTPS/UDP)
- HTTP tracker requests with proper URL encoding
- UDP tracker protocol implementation (BEP 15)
- Automatic fallback between tracker types
- Peer list parsing and management

### 4. peer_complete.py
**Purpose**: Peer wire protocol implementation
- TCP connection management with peers
- BitTorrent handshake protocol
- Message parsing and handling (choke, unchoke, interested, etc.)
- Piece request/response coordination
- Bitfield management for piece availability

### 5. piece_manager_complete.py
**Purpose**: Piece downloading coordination
- Piece and block management
- Rarest-first piece selection strategy
- SHA1 verification of completed pieces
- Download progress tracking
- Request queue management

### 6. file_manager_complete.py
**Purpose**: File I/O operations
- Piece-to-file mapping for multi-file torrents
- Directory creation and file allocation
- Efficient read/write operations
- Resume capability for partial downloads

### 7. progress_complete.py
**Purpose**: Progress tracking and display
- Real-time progress bars and statistics
- Download speed calculation
- ETA estimation
- Peer connection monitoring
- File-level progress for multi-file torrents

## Protocol Compliance

This implementation follows these BitTorrent Enhancement Proposals (BEPs):

- **BEP 3**: The BitTorrent Protocol Specification
- **BEP 15**: UDP Tracker Protocol for BitTorrent

### Key Protocol Features

1. **Torrent File Parsing**: Complete bencoding support for .torrent files
2. **Info Hash Calculation**: SHA1 hash of the info dictionary for tracker communication
3. **Tracker Communication**: Both HTTP and UDP tracker protocols
4. **Peer Handshake**: 68-byte handshake with protocol identification
5. **Message Protocol**: All standard peer wire messages (choke, unchoke, interested, not interested, have, bitfield, request, piece, cancel)
6. **Piece Verification**: SHA1 verification of each downloaded piece
7. **Multi-File Support**: Proper handling of multi-file torrents with directory structure

## Architecture

### Threading Model

The client uses a multi-threaded architecture:

- **Main Thread**: Coordination and progress display
- **Peer Threads**: One thread per peer connection
- **Tracker Thread**: Periodic tracker communication
- **Progress Thread**: Real-time progress updates

### Data Flow

1. **Torrent Parsing**: Load and parse .torrent file
2. **Tracker Contact**: Get initial peer list from trackers
3. **Peer Connection**: Establish connections with peers
4. **Piece Download**: Download pieces using rarest-first strategy
5. **File Writing**: Write completed pieces to appropriate files
6. **Progress Tracking**: Update progress and statistics

### Error Handling

- Network timeouts and connection failures
- Invalid torrent files and data corruption
- Tracker communication errors
- Peer protocol violations
- File system errors

## Performance Considerations

- **Concurrent Connections**: Configurable maximum peer connections
- **Memory Usage**: Efficient piece buffering and file operations
- **Network Optimization**: Request pipelining and bandwidth management
- **CPU Usage**: Optimized SHA1 verification and data processing

## Logging

The client provides comprehensive logging:

- **DEBUG**: Detailed protocol messages and internal state
- **INFO**: General progress and milestone information
- **WARNING**: Non-fatal issues and recoverable errors
- **ERROR**: Fatal errors and failures

## Troubleshooting

### Common Issues

1. **No peers found**: Check torrent file validity and tracker availability
2. **Slow downloads**: Increase max-peers or check network connectivity
3. **Permission errors**: Ensure write permissions in download directory
4. **Port conflicts**: Change the default port using --port option

### Debug Mode

Enable debug logging to see detailed protocol information:

```bash
python main_complete.py file.torrent --log-level DEBUG
```

## Development

### Code Structure

Each module is designed to be:
- **Self-contained**: Minimal dependencies between modules
- **Testable**: Clear interfaces for unit testing
- **Extensible**: Easy to add new features or protocols
- **Maintainable**: Clean code with comprehensive documentation

### Adding Features

To extend the client:
1. **New Protocols**: Add new tracker types in tracker_complete.py
2. **Optimizations**: Enhance piece selection in piece_manager_complete.py
3. **UI Improvements**: Modify progress display in progress_complete.py

## License

This implementation is provided for educational purposes and follows the open BitTorrent protocol specifications.

## Contributing

Contributions are welcome! Please ensure:
- Code follows existing style and patterns
- New features include appropriate logging
- Error handling is comprehensive
- Documentation is updated

## Acknowledgments

- BitTorrent protocol specification authors
- Python BitTorrent library developers
- Open source BitTorrent client projects
