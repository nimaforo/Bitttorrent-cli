"""
BitTorrent Torrent File Parser

This module handles parsing .torrent files and extracting metadata according to
the BitTorrent protocol specification. It supports both single-file and multi-file
torrents and provides access to all torrent metadata.

Author: BitTorrent CLI Client
"""

import bcoding
import hashlib
import os
from typing import List, Dict, Union, Optional


class TorrentFile:
    """
    Represents a single file within a torrent.
    """
    def __init__(self, path: List[str], length: int, md5sum: Optional[str] = None):
        self.path = path  # List of path components
        self.length = length  # File size in bytes
        self.md5sum = md5sum  # Optional MD5 checksum
        
    @property
    def name(self) -> str:
        """Get the filename (last component of path)."""
        return self.path[-1] if self.path else ""
    
    @property
    def full_path(self) -> str:
        """Get the full relative path as a string."""
        return os.path.join(*self.path) if self.path else ""


class Torrent:
    """
    BitTorrent torrent file parser and metadata container.
    
    Parses .torrent files according to the BitTorrent protocol specification
    and provides access to torrent metadata including files, trackers, and
    piece information.
    """
    
    def __init__(self, torrent_path: str):
        """
        Initialize torrent from .torrent file.
        
        Args:
            torrent_path: Path to the .torrent file
            
        Raises:
            FileNotFoundError: If torrent file doesn't exist
            ValueError: If torrent file is invalid or corrupted
        """
        self.torrent_path = torrent_path
        self._raw_data = None
        self._info_hash = None
        
        # Torrent metadata
        self.announce = None
        self.announce_list = []
        self.comment = None
        self.created_by = None
        self.creation_date = None
        self.encoding = None
        
        # Info dictionary fields
        self.name = None
        self.piece_length = None
        self.pieces = None
        self.files = []
        self.length = None  # For single-file torrents
        self.md5sum = None  # For single-file torrents
        
        # Parse the torrent file
        self._parse_torrent_file()
    
    def _parse_torrent_file(self):
        """Parse the torrent file and extract metadata."""
        try:
            with open(self.torrent_path, 'rb') as f:
                self._raw_data = bcoding.bdecode(f.read())
        except FileNotFoundError:
            raise FileNotFoundError(f"Torrent file not found: {self.torrent_path}")
        except Exception as e:
            raise ValueError(f"Failed to parse torrent file: {e}")
        
        # Extract top-level fields
        self.announce = self._safe_decode(self._raw_data.get('announce'))
        self.comment = self._safe_decode(self._raw_data.get('comment'))
        self.created_by = self._safe_decode(self._raw_data.get('created by'))
        self.creation_date = self._raw_data.get('creation date')
        self.encoding = self._safe_decode(self._raw_data.get('encoding'))
        
        # Extract announce-list (multi-tracker)
        if 'announce-list' in self._raw_data:
            self.announce_list = []
            for tier in self._raw_data['announce-list']:
                tier_list = []
                for tracker in tier:
                    tier_list.append(self._safe_decode(tracker))
                self.announce_list.append(tier_list)
        
        # Extract info dictionary
        self._parse_info_dict()
    
    def _parse_info_dict(self):
        """Parse the info dictionary containing file and piece information."""
        if 'info' not in self._raw_data:
            raise ValueError("Invalid torrent file: missing 'info' dictionary")
        
        info = self._raw_data['info']
        
        # Basic info fields
        self.name = self._safe_decode(info.get('name', b''))
        self.piece_length = info.get('piece length', 0)
        self.pieces = info.get('pieces', b'')
        
        # Check if this is a single-file or multi-file torrent
        if 'files' in info:
            # Multi-file torrent
            self._parse_multi_file_torrent(info)
        else:
            # Single-file torrent
            self._parse_single_file_torrent(info)
    
    def _parse_single_file_torrent(self, info: Dict):
        """Parse single-file torrent metadata."""
        self.length = info.get('length', 0)
        self.md5sum = self._safe_decode(info.get('md5sum'))
        
        # Create a single TorrentFile object
        self.files = [TorrentFile(
            path=[self.name],
            length=self.length,
            md5sum=self.md5sum
        )]
    
    def _parse_multi_file_torrent(self, info: Dict):
        """Parse multi-file torrent metadata."""
        self.files = []
        
        for file_info in info.get('files', []):
            # Extract file path components
            path_components = []
            for component in file_info.get('path', []):
                path_components.append(self._safe_decode(component))
            
            # Create TorrentFile object
            torrent_file = TorrentFile(
                path=path_components,
                length=file_info.get('length', 0),
                md5sum=self._safe_decode(file_info.get('md5sum'))
            )
            
            self.files.append(torrent_file)
    
    def _safe_decode(self, data: Union[bytes, str, None]) -> Optional[str]:
        """Safely decode bytes to string with fallback encoding."""
        if data is None:
            return None
        if isinstance(data, str):
            return data
        if isinstance(data, bytes):
            try:
                return data.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    return data.decode('latin1')
                except UnicodeDecodeError:
                    return data.decode('utf-8', errors='replace')
        return str(data)
    
    @property
    def info_hash(self) -> bytes:
        """
        Get the SHA1 hash of the info dictionary.
        
        This is used as the unique identifier for the torrent in tracker
        communication and peer handshakes.
        
        Returns:
            20-byte SHA1 hash of the bencoded info dictionary
        """
        if self._info_hash is None:
            info_dict = self._raw_data['info']
            info_encoded = bcoding.bencode(info_dict)
            self._info_hash = hashlib.sha1(info_encoded).digest()
        return self._info_hash
    
    @property
    def info_hash_hex(self) -> str:
        """Get the info hash as a hexadecimal string."""
        return self.info_hash.hex()
    
    @property
    def total_length(self) -> int:
        """
        Get the total size of all files in the torrent.
        
        Returns:
            Total size in bytes
        """
        return sum(f.length for f in self.files)
    
    @property
    def num_pieces(self) -> int:
        """
        Get the number of pieces in the torrent.
        
        Returns:
            Number of pieces
        """
        return len(self.pieces) // 20  # Each piece hash is 20 bytes
    
    def get_piece_hash(self, piece_index: int) -> bytes:
        """
        Get the SHA1 hash for a specific piece.
        
        Args:
            piece_index: Zero-based piece index
            
        Returns:
            20-byte SHA1 hash for the piece
            
        Raises:
            IndexError: If piece_index is out of range
        """
        if piece_index < 0 or piece_index >= self.num_pieces:
            raise IndexError(f"Piece index {piece_index} out of range (0-{self.num_pieces-1})")
        
        start = piece_index * 20
        end = start + 20
        return self.pieces[start:end]
    
    def get_piece_length(self, piece_index: int) -> int:
        """
        Get the actual length of a specific piece.
        
        The last piece may be shorter than the standard piece length.
        
        Args:
            piece_index: Zero-based piece index
            
        Returns:
            Length of the piece in bytes
            
        Raises:
            IndexError: If piece_index is out of range
        """
        if piece_index < 0 or piece_index >= self.num_pieces:
            raise IndexError(f"Piece index {piece_index} out of range (0-{self.num_pieces-1})")
        
        if piece_index == self.num_pieces - 1:
            # Last piece might be shorter
            return self.total_length - (piece_index * self.piece_length)
        else:
            return self.piece_length
    
    def get_all_trackers(self) -> List[str]:
        """
        Get all tracker URLs from announce and announce-list.
        
        Returns:
            List of all tracker URLs
        """
        trackers = []
        
        # Add primary tracker
        if self.announce:
            trackers.append(self.announce)
        
        # Add trackers from announce-list
        for tier in self.announce_list:
            for tracker in tier:
                if tracker not in trackers:
                    trackers.append(tracker)
        
        return trackers
    
    def is_single_file(self) -> bool:
        """
        Check if this is a single-file torrent.
        
        Returns:
            True if single-file, False if multi-file
        """
        return len(self.files) == 1 and self.files[0].path == [self.name]
    
    def __str__(self) -> str:
        """String representation of the torrent."""
        file_count = len(self.files)
        size_mb = self.total_length / (1024 * 1024)
        
        return (f"Torrent(name='{self.name}', "
                f"files={file_count}, "
                f"size={size_mb:.1f}MB, "
                f"pieces={self.num_pieces})")
    
    def __repr__(self) -> str:
        """Detailed string representation."""
        return self.__str__()


def create_torrent_file(files: List[str], announce: str, piece_length: int = 262144,
                       comment: str = None, name: str = None) -> bytes:
    """
    Create a .torrent file from a list of files.
    
    Args:
        files: List of file paths to include
        announce: Primary tracker URL
        piece_length: Size of each piece in bytes (default: 256KB)
        comment: Optional comment
        name: Optional name (defaults to basename of first file)
        
    Returns:
        Bencoded torrent data as bytes
        
    Note:
        This is a utility function for creating torrents. The main client
        focuses on downloading existing torrents.
    """
    # This is a simplified implementation for completeness
    # A full implementation would handle multi-file torrents properly
    
    if not files:
        raise ValueError("At least one file must be specified")
    
    file_path = files[0]  # Simplified: only handle single file
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Calculate pieces
    pieces = b''
    file_length = 0
    
    with open(file_path, 'rb') as f:
        while True:
            piece_data = f.read(piece_length)
            if not piece_data:
                break
            
            file_length += len(piece_data)
            piece_hash = hashlib.sha1(piece_data).digest()
            pieces += piece_hash
    
    # Build torrent dictionary
    torrent_dict = {
        'announce': announce.encode('utf-8'),
        'info': {
            'name': (name or os.path.basename(file_path)).encode('utf-8'),
            'length': file_length,
            'piece length': piece_length,
            'pieces': pieces
        }
    }
    
    if comment:
        torrent_dict['comment'] = comment.encode('utf-8')
    
    return bcoding.bencode(torrent_dict)


if __name__ == "__main__":
    # Example usage and testing
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python torrent.py <torrent_file>")
        sys.exit(1)
    
    try:
        torrent = Torrent(sys.argv[1])
        
        print(f"Torrent Analysis")
        print(f"================")
        print(f"Name: {torrent.name}")
        print(f"Total Size: {torrent.total_length / (1024*1024):.2f} MB")
        print(f"Piece Length: {torrent.piece_length / 1024:.0f} KB")
        print(f"Number of Pieces: {torrent.num_pieces}")
        print(f"Info Hash: {torrent.info_hash_hex}")
        print(f"Primary Tracker: {torrent.announce}")
        print(f"File Type: {'Single-file' if torrent.is_single_file() else 'Multi-file'}")
        
        if not torrent.is_single_file():
            print(f"Files ({len(torrent.files)}):")
            for i, file in enumerate(torrent.files[:10]):  # Show first 10 files
                print(f"  {i+1:2d}. {file.full_path} ({file.length / (1024*1024):.2f} MB)")
            if len(torrent.files) > 10:
                print(f"  ... and {len(torrent.files) - 10} more files")
        
        if torrent.announce_list:
            print(f"Backup Trackers: {len(sum(torrent.announce_list, []))} total")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
