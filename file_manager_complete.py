"""
BitTorrent File Management System

This module handles file I/O operations for BitTorrent downloads, including
creating directory structures, mapping pieces to files, and managing
file boundaries across pieces.

Author: BitTorrent CLI Client
"""

import os
import threading
from typing import Dict, List, Optional, Tuple
import logging


class FileManager:
    """
    Manages file I/O operations for BitTorrent downloads.
    
    Handles both single-file and multi-file torrents, creating appropriate
    directory structures and managing piece-to-file mapping.
    """
    
    def __init__(self, torrent, download_dir: str):
        """
        Initialize file manager.
        
        Args:
            torrent: Torrent object containing file information
            download_dir: Base directory for downloads
        """
        self.torrent = torrent
        self.download_dir = download_dir
        
        # File mapping
        self.file_handles: Dict[str, any] = {}
        self.file_info: List[Dict] = []
        
        # Threading
        self.lock = threading.RLock()
        
        # Setup logging
        self.logger = logging.getLogger("FileManager")
        
        # Initialize file structure
        self._initialize_files()
    
    def _initialize_files(self):
        """Initialize file structure and mapping."""
        # Create download directory
        os.makedirs(self.download_dir, exist_ok=True)
        
        # Build file information list
        offset = 0
        
        if self.torrent.is_single_file():
            # Single file torrent
            file_path = os.path.join(self.download_dir, self.torrent.name)
            file_info = {
                'path': file_path,
                'length': self.torrent.files[0].length,
                'offset': 0
            }
            self.file_info.append(file_info)
            
        else:
            # Multi-file torrent
            torrent_dir = os.path.join(self.download_dir, self.torrent.name)
            
            for torrent_file in self.torrent.files:
                # Build full file path
                file_path = os.path.join(torrent_dir, torrent_file.full_path)
                
                # Create directory structure
                file_dir = os.path.dirname(file_path)
                os.makedirs(file_dir, exist_ok=True)
                
                file_info = {
                    'path': file_path,
                    'length': torrent_file.length,
                    'offset': offset
                }
                self.file_info.append(file_info)
                
                offset += torrent_file.length
        
        self.logger.info(f"Initialized {len(self.file_info)} files in {self.download_dir}")
    
    def write_piece(self, piece_index: int, piece_data: bytes) -> bool:
        """
        Write a complete piece to the appropriate files.
        
        Args:
            piece_index: Index of the piece
            piece_data: Complete piece data
            
        Returns:
            True if write successful
        """
        with self.lock:
            try:
                # Calculate piece offset in the entire torrent
                piece_offset = piece_index * self.torrent.piece_length
                remaining_data = piece_data
                data_offset = 0
                
                # Find files that this piece spans
                for file_info in self.file_info:
                    file_start = file_info['offset']
                    file_end = file_start + file_info['length']
                    
                    # Check if piece overlaps with this file
                    if piece_offset < file_end and piece_offset + len(piece_data) > file_start:
                        # Calculate overlap
                        write_start = max(0, piece_offset - file_start)
                        write_end = min(file_info['length'], piece_offset + len(piece_data) - file_start)
                        
                        if write_start < write_end:
                            # Calculate data slice
                            data_start = max(0, file_start - piece_offset)
                            data_end = data_start + (write_end - write_start)
                            
                            file_data = piece_data[data_start:data_end]
                            
                            # Write to file
                            self._write_file_data(file_info['path'], write_start, file_data)
                
                self.logger.debug(f"Wrote piece {piece_index} ({len(piece_data)} bytes)")
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to write piece {piece_index}: {e}")
                return False
    
    def read_piece(self, piece_index: int) -> Optional[bytes]:
        """
        Read a complete piece from files.
        
        Args:
            piece_index: Index of the piece to read
            
        Returns:
            Piece data or None if read failed
        """
        with self.lock:
            try:
                piece_length = self.torrent.get_piece_length(piece_index)
                piece_offset = piece_index * self.torrent.piece_length
                piece_data = bytearray(piece_length)
                
                # Read from files that contain this piece
                for file_info in self.file_info:
                    file_start = file_info['offset']
                    file_end = file_start + file_info['length']
                    
                    # Check if piece overlaps with this file
                    if piece_offset < file_end and piece_offset + piece_length > file_start:
                        # Calculate overlap
                        read_start = max(0, piece_offset - file_start)
                        read_end = min(file_info['length'], piece_offset + piece_length - file_start)
                        
                        if read_start < read_end:
                            # Calculate data position in piece
                            data_start = max(0, file_start - piece_offset)
                            data_end = data_start + (read_end - read_start)
                            
                            # Read file data
                            file_data = self._read_file_data(file_info['path'], read_start, read_end - read_start)
                            
                            if file_data:
                                piece_data[data_start:data_end] = file_data
                            else:
                                return None
                
                return bytes(piece_data)
                
            except Exception as e:
                self.logger.debug(f"Failed to read piece {piece_index}: {e}")
                return None
    
    def read_block(self, piece_index: int, block_offset: int, block_length: int) -> Optional[bytes]:
        """
        Read a block from a piece.
        
        Args:
            piece_index: Index of the piece
            block_offset: Offset within the piece
            block_length: Length of the block
            
        Returns:
            Block data or None if read failed
        """
        # For simplicity, read the entire piece and extract the block
        piece_data = self.read_piece(piece_index)
        
        if piece_data and block_offset + block_length <= len(piece_data):
            return piece_data[block_offset:block_offset + block_length]
        
        return None
    
    def _write_file_data(self, file_path: str, offset: int, data: bytes):
        """
        Write data to a specific offset in a file.
        
        Args:
            file_path: Path to the file
            offset: Offset within the file
            data: Data to write
        """
        # Ensure file exists and has correct size
        if not os.path.exists(file_path):
            # Create file with correct size
            file_size = self._get_file_size(file_path)
            with open(file_path, 'wb') as f:
                f.seek(file_size - 1)
                f.write(b'\x00')
        
        # Write data at offset
        with open(file_path, 'r+b') as f:
            f.seek(offset)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())  # Force write to disk
    
    def _read_file_data(self, file_path: str, offset: int, length: int) -> Optional[bytes]:
        """
        Read data from a specific offset in a file.
        
        Args:
            file_path: Path to the file
            offset: Offset within the file
            length: Length of data to read
            
        Returns:
            File data or None if read failed
        """
        try:
            if not os.path.exists(file_path):
                return None
            
            with open(file_path, 'rb') as f:
                f.seek(offset)
                data = f.read(length)
                
                # Return None if we couldn't read the expected amount
                if len(data) != length:
                    return None
                
                return data
                
        except Exception:
            return None
    
    def _get_file_size(self, file_path: str) -> int:
        """Get the expected size of a file."""
        for file_info in self.file_info:
            if file_info['path'] == file_path:
                return file_info['length']
        return 0
    
    def create_files(self):
        """Create all files with their full sizes (for seeding)."""
        with self.lock:
            for file_info in self.file_info:
                file_path = file_info['path']
                file_length = file_info['length']
                
                if not os.path.exists(file_path):
                    # Create directory if needed
                    file_dir = os.path.dirname(file_path)
                    os.makedirs(file_dir, exist_ok=True)
                    
                    # Create file with correct size
                    with open(file_path, 'wb') as f:
                        if file_length > 0:
                            f.seek(file_length - 1)
                            f.write(b'\x00')
                    
                    self.logger.debug(f"Created file: {file_path} ({file_length} bytes)")
    
    def verify_files(self) -> bool:
        """
        Verify that all files exist and have correct sizes.
        
        Returns:
            True if all files are valid
        """
        with self.lock:
            for file_info in self.file_info:
                file_path = file_info['path']
                expected_size = file_info['length']
                
                if not os.path.exists(file_path):
                    self.logger.warning(f"Missing file: {file_path}")
                    return False
                
                actual_size = os.path.getsize(file_path)
                if actual_size != expected_size:
                    self.logger.warning(f"Size mismatch for {file_path}: "
                                      f"expected {expected_size}, got {actual_size}")
                    return False
            
            return True
    
    def get_completion_status(self) -> Dict[str, Dict]:
        """
        Get completion status for each file.
        
        Returns:
            Dictionary mapping file paths to status information
        """
        status = {}
        
        with self.lock:
            for file_info in self.file_info:
                file_path = file_info['path']
                expected_size = file_info['length']
                
                if os.path.exists(file_path):
                    actual_size = os.path.getsize(file_path)
                    exists = True
                else:
                    actual_size = 0
                    exists = False
                
                status[file_path] = {
                    'exists': exists,
                    'expected_size': expected_size,
                    'actual_size': actual_size,
                    'complete': exists and actual_size == expected_size
                }
        
        return status
    
    def cleanup(self):
        """Clean up resources and close file handles."""
        with self.lock:
            # Close any open file handles
            for handle in self.file_handles.values():
                try:
                    handle.close()
                except:
                    pass
            
            self.file_handles.clear()
            self.logger.debug("File manager cleanup complete")
    
    def get_total_size(self) -> int:
        """Get total size of all files."""
        return sum(file_info['length'] for file_info in self.file_info)
    
    def get_downloaded_size(self) -> int:
        """Get total size of downloaded data."""
        total = 0
        
        with self.lock:
            for file_info in self.file_info:
                file_path = file_info['path']
                
                if os.path.exists(file_path):
                    total += os.path.getsize(file_path)
        
        return total
    
    def remove_incomplete_files(self):
        """Remove files that are not completely downloaded."""
        with self.lock:
            for file_info in self.file_info:
                file_path = file_info['path']
                expected_size = file_info['length']
                
                if os.path.exists(file_path):
                    actual_size = os.path.getsize(file_path)
                    
                    if actual_size != expected_size:
                        try:
                            os.remove(file_path)
                            self.logger.info(f"Removed incomplete file: {file_path}")
                        except Exception as e:
                            self.logger.warning(f"Failed to remove {file_path}: {e}")
    
    def __str__(self) -> str:
        """String representation of file manager."""
        total_files = len(self.file_info)
        total_size = self.get_total_size()
        downloaded_size = self.get_downloaded_size()
        
        return (f"FileManager(files={total_files}, "
                f"size={total_size / (1024*1024):.1f}MB, "
                f"downloaded={downloaded_size / (1024*1024):.1f}MB)")


if __name__ == "__main__":
    # Example usage and testing
    print("BitTorrent File Management System")
    print("This module is designed to be used as part of a BitTorrent client.")
    print("Run the main client to see file management in action.")
