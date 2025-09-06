#!/usr/bin/env python3
"""
BitTorrent File Manager

This module handles file I/O operations, directory structure creation,
and mapping between pieces and files for both single and multi-file torrents.
"""

import os
import hashlib
import threading
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path


class FileManager:
    """Manages file I/O operations for torrent downloads."""
    
    def __init__(self, torrent_info, download_dir: str):
        """
        Initialize file manager.
        
        Args:
            torrent_info: TorrentFile object with torrent metadata
            download_dir: Base directory for downloads
        """
        self.torrent_info = torrent_info
        self.download_dir = Path(download_dir)
        self.torrent_dir = self.download_dir / torrent_info.name
        
        self.file_handles = {}  # {file_path: file_handle}
        self.file_lock = threading.RLock()
        self.logger = logging.getLogger(__name__)
        
        # Create directory structure
        self._setup_directory_structure()
        
        # Map file information
        self.file_info = self._setup_file_mapping()
    
    def _setup_directory_structure(self):
        """Create necessary directory structure."""
        try:
            if self.torrent_info.is_multi_file():
                # Multi-file torrent: create base directory
                self.torrent_dir.mkdir(parents=True, exist_ok=True)
                
                # Create subdirectories for each file
                for file_info in self.torrent_info.files:
                    file_path = self.torrent_dir / file_info['path']
                    file_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                # Single-file torrent: create parent directory
                self.download_dir.mkdir(parents=True, exist_ok=True)
            
            self.logger.info(f"Directory structure created in {self.download_dir}")
            
        except Exception as e:
            self.logger.error(f"Failed to create directory structure: {e}")
            raise
    
    def _setup_file_mapping(self) -> List[Dict]:
        """Setup file mapping with full paths and offsets."""
        file_info = []
        current_offset = 0
        
        for i, file_data in enumerate(self.torrent_info.files):
            if self.torrent_info.is_multi_file():
                file_path = self.torrent_dir / file_data['path']
            else:
                file_path = self.download_dir / file_data['path']
            
            file_info.append({
                'index': i,
                'path': file_path,
                'length': file_data['length'],
                'start_offset': current_offset,
                'end_offset': current_offset + file_data['length']
            })
            
            current_offset += file_data['length']
        
        return file_info
    
    def _get_file_handle(self, file_path: Path, mode: str = 'r+b') -> Optional[object]:
        """Get file handle with caching."""
        with self.file_lock:
            str_path = str(file_path)
            
            if str_path in self.file_handles:
                return self.file_handles[str_path]
            
            try:
                # Create file if it doesn't exist
                if not file_path.exists():
                    with open(file_path, 'wb') as f:
                        pass  # Create empty file
                
                file_handle = open(file_path, mode)
                self.file_handles[str_path] = file_handle
                return file_handle
                
            except Exception as e:
                self.logger.error(f"Failed to open file {file_path}: {e}")
                return None
    
    def write_piece(self, piece_index: int, piece_data: bytes) -> bool:
        """
        Write a completed piece to disk.
        
        Args:
            piece_index: Index of the piece
            piece_data: Complete piece data
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get file segments for this piece
            segments = self.torrent_info.get_file_segments(piece_index)
            
            for segment in segments:
                file_info = self.file_info[segment['file_index']]
                file_handle = self._get_file_handle(file_info['path'])
                
                if not file_handle:
                    self.logger.error(f"Failed to get file handle for {file_info['path']}")
                    return False
                
                # Extract data for this segment
                segment_data = piece_data[segment['piece_offset']:
                                        segment['piece_offset'] + segment['length']]
                
                # Write to file
                file_handle.seek(segment['file_offset'])
                file_handle.write(segment_data)
                file_handle.flush()
            
            self.logger.debug(f"Piece {piece_index} written to disk")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to write piece {piece_index}: {e}")
            return False
    
    def read_piece(self, piece_index: int) -> Optional[bytes]:
        """
        Read a piece from disk.
        
        Args:
            piece_index: Index of the piece
            
        Returns:
            Piece data or None if failed
        """
        try:
            piece_size = self.torrent_info.get_piece_size(piece_index)
            piece_data = bytearray(piece_size)
            
            segments = self.torrent_info.get_file_segments(piece_index)
            
            for segment in segments:
                file_info = self.file_info[segment['file_index']]
                file_handle = self._get_file_handle(file_info['path'])
                
                if not file_handle:
                    return None
                
                # Read segment data
                file_handle.seek(segment['file_offset'])
                segment_data = file_handle.read(segment['length'])
                
                if len(segment_data) != segment['length']:
                    self.logger.warning(f"Incomplete read for piece {piece_index}, segment {segment}")
                    return None
                
                # Copy to piece data
                piece_data[segment['piece_offset']:
                          segment['piece_offset'] + segment['length']] = segment_data
            
            return bytes(piece_data)
            
        except Exception as e:
            self.logger.error(f"Failed to read piece {piece_index}: {e}")
            return None
    
    def verify_piece(self, piece_index: int) -> bool:
        """
        Verify a piece against its SHA1 hash.
        
        Args:
            piece_index: Index of the piece
            
        Returns:
            True if piece is valid, False otherwise
        """
        try:
            piece_data = self.read_piece(piece_index)
            if not piece_data:
                return False
            
            expected_hash = self.torrent_info.get_piece_hash(piece_index)
            actual_hash = hashlib.sha1(piece_data).digest()
            
            return actual_hash == expected_hash
            
        except Exception as e:
            self.logger.error(f"Failed to verify piece {piece_index}: {e}")
            return False
    
    def check_existing_pieces(self) -> List[int]:
        """
        Check which pieces already exist and are valid.
        Used for resume functionality.
        
        Returns:
            List of valid piece indices
        """
        valid_pieces = []
        
        for piece_index in range(self.torrent_info.num_pieces):
            if self._piece_exists(piece_index) and self.verify_piece(piece_index):
                valid_pieces.append(piece_index)
        
        self.logger.info(f"Found {len(valid_pieces)} existing valid pieces")
        return valid_pieces
    
    def _piece_exists(self, piece_index: int) -> bool:
        """Check if all files for a piece exist and have sufficient size."""
        try:
            segments = self.torrent_info.get_file_segments(piece_index)
            
            for segment in segments:
                file_info = self.file_info[segment['file_index']]
                
                if not file_info['path'].exists():
                    return False
                
                file_size = file_info['path'].stat().st_size
                required_size = segment['file_offset'] + segment['length']
                
                if file_size < required_size:
                    return False
            
            return True
            
        except Exception:
            return False
    
    def get_download_progress(self) -> Dict:
        """
        Get download progress information.
        
        Returns:
            Dictionary with progress information
        """
        total_size = 0
        downloaded_size = 0
        
        for file_info in self.file_info:
            total_size += file_info['length']
            
            if file_info['path'].exists():
                downloaded_size += min(file_info['path'].stat().st_size, file_info['length'])
        
        progress_percentage = (downloaded_size / total_size * 100) if total_size > 0 else 0
        
        return {
            'total_size': total_size,
            'downloaded_size': downloaded_size,
            'progress_percentage': progress_percentage,
            'files_total': len(self.file_info),
            'files_completed': sum(1 for f in self.file_info if self._file_complete(f))
        }
    
    def _file_complete(self, file_info: Dict) -> bool:
        """Check if a file is completely downloaded."""
        if not file_info['path'].exists():
            return False
        
        return file_info['path'].stat().st_size >= file_info['length']
    
    def get_file_list(self) -> List[Dict]:
        """Get list of files with their status."""
        files = []
        
        for file_info in self.file_info:
            file_size = 0
            if file_info['path'].exists():
                file_size = file_info['path'].stat().st_size
            
            files.append({
                'path': str(file_info['path']),
                'total_size': file_info['length'],
                'downloaded_size': min(file_size, file_info['length']),
                'progress': (min(file_size, file_info['length']) / file_info['length'] * 100),
                'complete': file_size >= file_info['length']
            })
        
        return files
    
    def allocate_files(self, sparse: bool = True) -> bool:
        """
        Pre-allocate space for all files.
        
        Args:
            sparse: Use sparse files (faster) or allocate full size
            
        Returns:
            True if successful
        """
        try:
            for file_info in self.file_info:
                if not file_info['path'].exists():
                    # Create file
                    with open(file_info['path'], 'wb') as f:
                        if not sparse:
                            # Write zeros to allocate full size
                            f.write(b'\x00' * file_info['length'])
                        else:
                            # Just seek to end to create sparse file
                            f.seek(file_info['length'] - 1)
                            f.write(b'\x00')
                
                self.logger.debug(f"Allocated file: {file_info['path']}")
            
            self.logger.info("File allocation completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to allocate files: {e}")
            return False
    
    def close_all_files(self):
        """Close all open file handles."""
        with self.file_lock:
            for file_path, file_handle in self.file_handles.items():
                try:
                    file_handle.close()
                    self.logger.debug(f"Closed file: {file_path}")
                except Exception as e:
                    self.logger.error(f"Error closing file {file_path}: {e}")
            
            self.file_handles.clear()
            self.logger.info("All file handles closed")
    
    def get_storage_info(self) -> Dict:
        """Get storage information."""
        try:
            # Get available space (Windows and Unix compatible)
            if os.name == 'nt':  # Windows
                import shutil
                total, used, available = shutil.disk_usage(self.download_dir)
                available_space = available
            else:  # Unix/Linux
                statvfs = os.statvfs(self.download_dir)
                available_space = statvfs.f_frsize * statvfs.f_bavail
            
            # Calculate required space
            required_space = self.torrent_info.total_size
            
            # Calculate used space
            used_space = 0
            for file_info in self.file_info:
                if file_info['path'].exists():
                    used_space += file_info['path'].stat().st_size
            
            return {
                'download_dir': str(self.download_dir),
                'torrent_dir': str(self.torrent_dir),
                'required_space': required_space,
                'used_space': used_space,
                'available_space': available_space,
                'sufficient_space': available_space >= (required_space - used_space)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get storage info: {e}")
            # Return default values that assume sufficient space
            return {
                'download_dir': str(self.download_dir),
                'torrent_dir': str(self.torrent_dir),
                'required_space': self.torrent_info.total_size,
                'used_space': 0,
                'available_space': self.torrent_info.total_size * 2,  # Assume enough space
                'sufficient_space': True
            }
    
    def cleanup_partial_files(self):
        """Remove incomplete files (useful for cleanup)."""
        removed_files = 0
        
        for file_info in self.file_info:
            if file_info['path'].exists():
                file_size = file_info['path'].stat().st_size
                
                if file_size < file_info['length']:
                    try:
                        file_info['path'].unlink()
                        removed_files += 1
                        self.logger.info(f"Removed partial file: {file_info['path']}")
                    except Exception as e:
                        self.logger.error(f"Failed to remove {file_info['path']}: {e}")
        
        self.logger.info(f"Cleaned up {removed_files} partial files")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close all files."""
        self.close_all_files()


if __name__ == "__main__":
    # Test file manager functionality
    import sys
    import tempfile
    
    if len(sys.argv) != 2:
        print("Usage: python file_manager_client.py <torrent_file>")
        sys.exit(1)
    
    logging.basicConfig(level=logging.DEBUG)
    
    from torrent_new import parse_torrent
    
    try:
        torrent = parse_torrent(sys.argv[1])
        
        # Use temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            file_manager = FileManager(torrent, temp_dir)
            
            print(f"Torrent: {torrent.name}")
            print(f"Download directory: {file_manager.download_dir}")
            print(f"Torrent directory: {file_manager.torrent_dir}")
            
            # Check storage info
            storage_info = file_manager.get_storage_info()
            print(f"\nStorage Info:")
            print(f"  Required space: {storage_info.get('required_space', 0):,} bytes")
            print(f"  Available space: {storage_info.get('available_space', 0):,} bytes")
            print(f"  Sufficient space: {storage_info.get('sufficient_space', False)}")
            
            # Check existing pieces
            existing_pieces = file_manager.check_existing_pieces()
            print(f"\nExisting valid pieces: {len(existing_pieces)}")
            
            # Get file list
            files = file_manager.get_file_list()
            print(f"\nFiles ({len(files)}):")
            for file_info in files[:5]:  # Show first 5 files
                print(f"  {file_info['path']} - {file_info['total_size']:,} bytes")
            
            if len(files) > 5:
                print(f"  ... and {len(files) - 5} more files")
            
            # Test file allocation (sparse)
            print(f"\nAllocating files...")
            if file_manager.allocate_files(sparse=True):
                print("File allocation successful")
            else:
                print("File allocation failed")
            
            file_manager.close_all_files()
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
