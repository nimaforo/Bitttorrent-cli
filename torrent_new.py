#!/usr/bin/env python3
"""
BitTorrent Torrent File Parser

This module handles parsing of .torrent files and provides metadata extraction
functionality for both single-file and multi-file torrents.
"""

import hashlib
import bcoding
import os
from typing import Dict, List, Optional, Union


class TorrentFile:
    """Represents a parsed torrent file with all metadata."""
    
    def __init__(self, torrent_path: str):
        """
        Initialize TorrentFile by parsing the .torrent file.
        
        Args:
            torrent_path: Path to the .torrent file
            
        Raises:
            FileNotFoundError: If torrent file doesn't exist
            ValueError: If torrent file is malformed
        """
        self.torrent_path = torrent_path
        self.torrent_data = self._parse_torrent_file(torrent_path)
        
        # Handle both byte and string keys
        info_key = b'info' if b'info' in self.torrent_data else 'info'
        self.info = self.torrent_data[info_key]
        
        # Calculate info hash
        self.info_hash = self._calculate_info_hash()
        
        # Extract basic metadata
        name_key = b'name' if b'name' in self.info else 'name'
        piece_length_key = b'piece length' if b'piece length' in self.info else 'piece length'
        pieces_key = b'pieces' if b'pieces' in self.info else 'pieces'
        
        self.name = self.info[name_key].decode('utf-8') if isinstance(self.info[name_key], bytes) else self.info[name_key]
        self.piece_length = self.info[piece_length_key]
        self.pieces = self.info[pieces_key]
        self.num_pieces = len(self.pieces) // 20  # Each hash is 20 bytes
        
        # Handle announce URLs
        self.announce_list = self._get_announce_list()
        
        # Determine if single or multi-file torrent
        self.files = self._get_files_info()
        self.total_size = self._calculate_total_size()
        
        # Create piece hashes list
        self.piece_hashes = [self.pieces[i:i+20] for i in range(0, len(self.pieces), 20)]
    
    def _parse_torrent_file(self, torrent_path: str) -> Dict:
        """Parse .torrent file using bcoding library."""
        if not os.path.exists(torrent_path):
            raise FileNotFoundError(f"Torrent file not found: {torrent_path}")
        
        try:
            with open(torrent_path, 'rb') as f:
                data = f.read()
                # Try different bcoding APIs
                try:
                    return bcoding.bdecode(data)
                except AttributeError:
                    try:
                        return bcoding.decode(data)
                    except AttributeError:
                        # Fallback to bencodepy if bcoding doesn't work
                        import bencodepy
                        return bencodepy.decode(data)
        except Exception as e:
            raise ValueError(f"Failed to parse torrent file: {e}")
    
    def _calculate_info_hash(self) -> bytes:
        """Calculate SHA1 hash of the info dictionary."""
        try:
            info_encoded = bcoding.bencode(self.info)
        except AttributeError:
            try:
                info_encoded = bcoding.encode(self.info)
            except AttributeError:
                import bencodepy
                info_encoded = bencodepy.encode(self.info)
        return hashlib.sha1(info_encoded).digest()
    
    def _get_announce_list(self) -> List[str]:
        """Extract announce URLs from torrent."""
        announce_list = []
        
        # Primary announce URL
        announce_key = b'announce' if b'announce' in self.torrent_data else 'announce'
        if announce_key in self.torrent_data:
            announce_url = self.torrent_data[announce_key]
            if isinstance(announce_url, bytes):
                announce_url = announce_url.decode('utf-8')
            announce_list.append(announce_url)
        
        # Additional announce URLs
        announce_list_key = b'announce-list' if b'announce-list' in self.torrent_data else 'announce-list'
        if announce_list_key in self.torrent_data:
            for tier in self.torrent_data[announce_list_key]:
                for url in tier:
                    url_str = url.decode('utf-8') if isinstance(url, bytes) else url
                    if url_str not in announce_list:
                        announce_list.append(url_str)
        
        return announce_list
    
    def _get_files_info(self) -> List[Dict]:
        """Extract file information for single or multi-file torrents."""
        files = []
        
        files_key = b'files' if b'files' in self.info else 'files'
        if files_key in self.info:
            # Multi-file torrent
            for file_info in self.info[files_key]:
                path_key = b'path' if b'path' in file_info else 'path'
                length_key = b'length' if b'length' in file_info else 'length'
                
                path_parts = []
                for part in file_info[path_key]:
                    if isinstance(part, bytes):
                        path_parts.append(part.decode('utf-8'))
                    else:
                        path_parts.append(part)
                
                files.append({
                    'path': os.path.join(*path_parts),
                    'length': file_info[length_key]
                })
        else:
            # Single-file torrent
            length_key = b'length' if b'length' in self.info else 'length'
            files.append({
                'path': self.name,
                'length': self.info[length_key]
            })
        
        return files
    
    def _calculate_total_size(self) -> int:
        """Calculate total size of all files in torrent."""
        return sum(file['length'] for file in self.files)
    
    def is_multi_file(self) -> bool:
        """Check if this is a multi-file torrent."""
        files_key = b'files' if b'files' in self.info else 'files'
        return files_key in self.info
    
    def get_piece_hash(self, piece_index: int) -> bytes:
        """Get SHA1 hash for a specific piece."""
        if piece_index < 0 or piece_index >= self.num_pieces:
            raise IndexError(f"Piece index {piece_index} out of range")
        return self.piece_hashes[piece_index]
    
    def get_piece_size(self, piece_index: int) -> int:
        """Get size of a specific piece (last piece may be smaller)."""
        if piece_index < 0 or piece_index >= self.num_pieces:
            raise IndexError(f"Piece index {piece_index} out of range")
        
        if piece_index == self.num_pieces - 1:
            # Last piece may be smaller
            return self.total_size - (piece_index * self.piece_length)
        else:
            return self.piece_length
    
    def get_file_segments(self, piece_index: int) -> List[Dict]:
        """
        Get file segments that a piece spans across.
        
        Returns:
            List of dicts with 'file_index', 'file_offset', 'piece_offset', 'length'
        """
        piece_start = piece_index * self.piece_length
        piece_size = self.get_piece_size(piece_index)
        piece_end = piece_start + piece_size
        
        segments = []
        current_offset = 0
        
        for file_index, file_info in enumerate(self.files):
            file_start = current_offset
            file_end = current_offset + file_info['length']
            
            # Check if piece overlaps with this file
            if piece_start < file_end and piece_end > file_start:
                segment_start = max(piece_start, file_start)
                segment_end = min(piece_end, file_end)
                
                segments.append({
                    'file_index': file_index,
                    'file_offset': segment_start - file_start,
                    'piece_offset': segment_start - piece_start,
                    'length': segment_end - segment_start
                })
            
            current_offset = file_end
            
            if current_offset >= piece_end:
                break
        
        return segments
    
    def __str__(self) -> str:
        """String representation of torrent info."""
        return (f"Torrent: {self.name}\n"
                f"Size: {self.total_size:,} bytes\n"
                f"Pieces: {self.num_pieces}\n"
                f"Piece Length: {self.piece_length:,} bytes\n"
                f"Files: {len(self.files)}\n"
                f"Type: {'Multi-file' if self.is_multi_file() else 'Single-file'}")


def parse_torrent(torrent_path: str) -> TorrentFile:
    """
    Convenience function to parse a torrent file.
    
    Args:
        torrent_path: Path to the .torrent file
        
    Returns:
        TorrentFile object with parsed metadata
    """
    return TorrentFile(torrent_path)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python torrent.py <torrent_file>")
        sys.exit(1)
    
    try:
        torrent = parse_torrent(sys.argv[1])
        print(torrent)
        print(f"\nInfo Hash: {torrent.info_hash.hex()}")
        print(f"Announce URLs: {len(torrent.announce_list)}")
        for i, url in enumerate(torrent.announce_list):
            print(f"  {i+1}. {url}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
