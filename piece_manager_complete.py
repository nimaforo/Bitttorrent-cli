"""
BitTorrent Piece Management System

This module manages piece downloading, verification, and coordination across
multiple peers. It handles the core logic for selecting which pieces to
download and ensuring data integrity.

Author: BitTorrent CLI Client
"""

import hashlib
import logging
import threading
import time
import random
from typing import Dict, List, Set, Tuple, Optional
from bitstring import BitArray
import logging


class PieceBlock:
    """Represents a block within a piece."""
    
    def __init__(self, offset: int, length: int, data: bytes = None):
        self.offset = offset
        self.length = length
        self.data = data
        self.requested = False
        self.received = False
        self.request_time = 0


class Piece:
    """Represents a torrent piece with its blocks."""
    
    BLOCK_SIZE = 16384  # 16KB standard block size
    
    def __init__(self, index: int, length: int, hash_value: bytes):
        self.index = index
        self.length = length
        self.hash_value = hash_value
        self.blocks: List[PieceBlock] = []
        self.completed = False
        self.verified = False
        self.last_activity = time.time()
        
        # Create blocks
        self._create_blocks()
    
    def _create_blocks(self):
        """Create blocks for this piece."""
        offset = 0
        while offset < self.length:
            block_length = min(self.BLOCK_SIZE, self.length - offset)
            block = PieceBlock(offset, block_length)
            self.blocks.append(block)
            offset += block_length
    
    def add_block(self, offset: int, data: bytes) -> bool:
        """
        Add block data to the piece.
        
        Args:
            offset: Block offset within piece
            data: Block data
            
        Returns:
            True if piece is now complete
        """
        # Find the block
        for block in self.blocks:
            if block.offset == offset:
                if len(data) != block.length:
                    return False
                
                block.data = data
                block.received = True
                self.last_activity = time.time()
                break
        else:
            return False  # Block not found
        
        # Check if piece is complete
        self.completed = all(block.received for block in self.blocks)
        
        if self.completed:
            # Verify piece integrity
            piece_data = self.get_data()
            piece_hash = hashlib.sha1(piece_data).digest()
            self.verified = piece_hash == self.hash_value
            
            if not self.verified:
                # Hash mismatch - reset piece
                self.reset()
                return False
        
        return self.completed and self.verified
    
    def get_data(self) -> bytes:
        """Get complete piece data."""
        if not self.completed:
            return b''
        
        data = b''
        for block in self.blocks:
            if block.data:
                data += block.data
        
        return data
    
    def reset(self):
        """Reset piece to initial state."""
        self.completed = False
        self.verified = False
        
        for block in self.blocks:
            block.data = None
            block.received = False
            block.requested = False
            block.request_time = 0
    
    def get_next_block_request(self) -> Optional[Tuple[int, int]]:
        """
        Get the next block to request.
        
        Returns:
            (offset, length) tuple or None if no blocks available
        """
        current_time = time.time()
        
        for block in self.blocks:
            if not block.received and not block.requested:
                block.requested = True
                block.request_time = current_time
                return (block.offset, block.length)
            elif block.requested and (current_time - block.request_time) > 60:
                # Re-request blocks that have been pending too long
                block.request_time = current_time
                return (block.offset, block.length)
        
        return None
    
    def cancel_block_request(self, offset: int):
        """Cancel a block request."""
        for block in self.blocks:
            if block.offset == offset:
                block.requested = False
                block.request_time = 0
                break
    
    @property
    def completion_percentage(self) -> float:
        """Get completion percentage."""
        if not self.blocks:
            return 0.0
        
        completed_blocks = sum(1 for block in self.blocks if block.received)
        return (completed_blocks / len(self.blocks)) * 100.0


class PieceManager:
    """
    Manages piece downloading and verification for a BitTorrent client.
    
    Coordinates piece selection, block requests, and data integrity
    verification across multiple peer connections.
    """
    
    def __init__(self, torrent, file_manager):
        """
        Initialize piece manager.
        
        Args:
            torrent: Torrent object containing piece information
            file_manager: FileManager for writing completed pieces
        """
        self.torrent = torrent
        self.file_manager = file_manager
        
        # Piece tracking
        self.pieces: Dict[int, Piece] = {}
        self.completed_pieces: Set[int] = set()
        self.have_pieces: BitArray = BitArray(length=torrent.num_pieces)
        
        # Request tracking
        self.pending_requests: Dict[Tuple[int, int], float] = {}  # (piece, offset) -> timestamp
        
        # Strategy configuration
        self.max_pending_pieces = 5
        self.request_timeout = 60
        
        # Statistics
        self.bytes_downloaded = 0
        self.pieces_completed = 0
        self.start_time = time.time()
        
        # Threading
        self.lock = threading.RLock()
        
        # Setup logging
        self.logger = logging.getLogger("PieceManager")
        
        # Initialize pieces
        self._initialize_pieces()
        
        # Check for existing pieces (resume support)
        self._check_existing_pieces()
        
        # Setup logging
        self.logger = logging.getLogger("PieceManager")
    
    def _initialize_pieces(self):
        """Initialize piece objects."""
        for i in range(self.torrent.num_pieces):
            piece_length = self.torrent.get_piece_length(i)
            piece_hash = self.torrent.get_piece_hash(i)
            
            piece = Piece(i, piece_length, piece_hash)
            self.pieces[i] = piece
    
    def _check_existing_pieces(self):
        """Check for existing pieces on disk (resume support)."""
        self.logger.info("Checking for existing pieces...")
        
        verified_count = 0
        
        for piece_index in range(self.torrent.num_pieces):
            try:
                # Try to read piece data from disk
                piece_data = self.file_manager.read_piece(piece_index)
                
                if piece_data and len(piece_data) == self.pieces[piece_index].length:
                    # Verify piece hash
                    piece_hash = hashlib.sha1(piece_data).digest()
                    expected_hash = self.torrent.get_piece_hash(piece_index)
                    
                    if piece_hash == expected_hash:
                        # Mark piece as completed
                        self._mark_piece_completed(piece_index)
                        verified_count += 1
                        
            except Exception as e:
                # Piece doesn't exist or is corrupted
                continue
        
        if verified_count > 0:
            completion = (verified_count / self.torrent.num_pieces) * 100
            self.logger.info(f"Found {verified_count} existing pieces ({completion:.1f}% complete)")
    
    def _mark_piece_completed(self, piece_index: int):
        """Mark a piece as completed."""
        with self.lock:
            self.completed_pieces.add(piece_index)
            self.have_pieces[piece_index] = True
            self.pieces[piece_index].completed = True
            self.pieces[piece_index].verified = True
            self.pieces_completed += 1
    
    def need_piece(self, piece_index: int) -> bool:
        """
        Check if we need a specific piece.
        
        Args:
            piece_index: Piece index to check
            
        Returns:
            True if we need this piece
        """
        with self.lock:
            return piece_index not in self.completed_pieces
    
    def have_piece(self, piece_index: int) -> bool:
        """
        Check if we have a specific piece.
        
        Args:
            piece_index: Piece index to check
            
        Returns:
            True if we have this piece
        """
        with self.lock:
            return piece_index in self.completed_pieces
    
    def get_next_request(self, peer_pieces: Set[int]) -> Optional[Tuple[int, int, int]]:
        """
        Get the next block request for a peer.
        
        Args:
            peer_pieces: Set of piece indices the peer has
            
        Returns:
            (piece_index, block_offset, block_length) tuple or None
        """
        with self.lock:
            # Find pieces we need that the peer has
            needed_pieces = []
            for piece_index in peer_pieces:
                if self.need_piece(piece_index):
                    needed_pieces.append(piece_index)
            
            if not needed_pieces:
                return None
            
            # Prioritize pieces using rarest first strategy
            piece_priorities = self._calculate_piece_priorities(needed_pieces)
            
            # Try to get a block from prioritized pieces
            for piece_index in piece_priorities:
                piece = self.pieces[piece_index]
                
                # Skip pieces with too many pending requests
                piece_pending = sum(1 for (p, _) in self.pending_requests if p == piece_index)
                if piece_pending >= 5:  # Limit concurrent requests per piece
                    continue
                
                # Get next block request
                block_request = piece.get_next_block_request()
                if block_request:
                    block_offset, block_length = block_request
                    
                    # Track request
                    self.pending_requests[(piece_index, block_offset)] = time.time()
                    
                    return (piece_index, block_offset, block_length)
            
            return None
    
    def _calculate_piece_priorities(self, piece_indices: List[int]) -> List[int]:
        """
        Calculate piece download priorities using rarest first strategy.
        
        Args:
            piece_indices: List of available piece indices
            
        Returns:
            Sorted list of piece indices by priority (highest first)
        """
        # For this implementation, we'll use a simple strategy:
        # 1. Prioritize pieces that are partially downloaded
        # 2. Then use random selection (simplified rarest first)
        
        partial_pieces = []
        empty_pieces = []
        
        for piece_index in piece_indices:
            piece = self.pieces[piece_index]
            
            if any(block.received for block in piece.blocks):
                partial_pieces.append(piece_index)
            else:
                empty_pieces.append(piece_index)
        
        # Shuffle for pseudo-random selection
        random.shuffle(partial_pieces)
        random.shuffle(empty_pieces)
        
        # Return partial pieces first, then empty pieces
        return partial_pieces + empty_pieces
    
    def add_block(self, piece_index: int, block_offset: int, block_data: bytes) -> bool:
        """
        Add a block to a piece.
        
        Args:
            piece_index: Piece index
            block_offset: Block offset within piece
            block_data: Block data
            
        Returns:
            True if piece was completed by this block
        """
        with self.lock:
            # Remove from pending requests
            request_key = (piece_index, block_offset)
            if request_key in self.pending_requests:
                del self.pending_requests[request_key]
            
            # Skip if we already have this piece
            if piece_index in self.completed_pieces:
                return False
            
            piece = self.pieces[piece_index]
            
            # Add block to piece
            piece_completed = piece.add_block(block_offset, block_data)
            
            # Update statistics
            self.bytes_downloaded += len(block_data)
            
            if piece_completed:
                # Piece is complete and verified
                self.logger.info(f"Piece {piece_index} completed and verified")
                
                # Write piece to disk
                try:
                    piece_data = piece.get_data()
                    self.file_manager.write_piece(piece_index, piece_data)
                    
                    # Mark as completed
                    self._mark_piece_completed(piece_index)
                    
                    return True
                    
                except Exception as e:
                    self.logger.error(f"Failed to write piece {piece_index}: {e}")
                    piece.reset()
                    return False
            
            return False
    
    def cancel_request(self, piece_index: int, block_offset: int):
        """
        Cancel a block request.
        
        Args:
            piece_index: Piece index
            block_offset: Block offset within piece
        """
        with self.lock:
            # Remove from pending requests
            request_key = (piece_index, block_offset)
            if request_key in self.pending_requests:
                del self.pending_requests[request_key]
            
            # Cancel in piece
            if piece_index in self.pieces:
                piece = self.pieces[piece_index]
                piece.cancel_block_request(block_offset)
    
    def cleanup_stale_requests(self):
        """Remove requests that have been pending too long."""
        with self.lock:
            current_time = time.time()
            stale_requests = []
            
            for (piece_index, block_offset), request_time in self.pending_requests.items():
                if current_time - request_time > self.request_timeout:
                    stale_requests.append((piece_index, block_offset))
            
            for piece_index, block_offset in stale_requests:
                self.cancel_request(piece_index, block_offset)
            
            if stale_requests:
                self.logger.debug(f"Cleaned up {len(stale_requests)} stale requests")
    
    def get_piece_availability(self, peer_bitfields: Dict) -> Dict[int, int]:
        """
        Calculate piece availability across all peers.
        
        Args:
            peer_bitfields: Dictionary mapping peer IDs to bitfields
            
        Returns:
            Dictionary mapping piece indices to availability count
        """
        availability = {}
        
        for piece_index in range(self.torrent.num_pieces):
            count = 0
            for bitfield in peer_bitfields.values():
                if piece_index < len(bitfield) and bitfield[piece_index]:
                    count += 1
            availability[piece_index] = count
        
        return availability
    
    def all_pieces_downloaded(self) -> bool:
        """
        Check if all pieces have been downloaded.
        
        Returns:
            True if download is complete
        """
        with self.lock:
            return len(self.completed_pieces) == self.torrent.num_pieces
    
    def get_progress(self) -> Dict[str, float]:
        """
        Get download progress information.
        
        Returns:
            Dictionary containing progress statistics
        """
        with self.lock:
            total_pieces = self.torrent.num_pieces
            completed_pieces = len(self.completed_pieces)
            
            # Calculate partial progress
            partial_bytes = 0
            total_bytes = self.torrent.total_length
            
            for piece in self.pieces.values():
                if not piece.completed:
                    for block in piece.blocks:
                        if block.received:
                            partial_bytes += len(block.data) if block.data else 0
            
            completed_bytes = sum(
                self.torrent.get_piece_length(i) for i in self.completed_pieces
            ) + partial_bytes
            
            # Calculate rates
            elapsed = time.time() - self.start_time
            download_rate = self.bytes_downloaded / elapsed if elapsed > 0 else 0
            
            return {
                'pieces_completed': completed_pieces,
                'total_pieces': total_pieces,
                'pieces_percentage': (completed_pieces / total_pieces) * 100,
                'bytes_completed': completed_bytes,
                'total_bytes': total_bytes,
                'bytes_percentage': (completed_bytes / total_bytes) * 100,
                'download_rate': download_rate,
                'pending_requests': len(self.pending_requests)
            }
    
    def get_bitfield(self) -> BitArray:
        """
        Get our current bitfield.
        
        Returns:
            BitArray representing pieces we have
        """
        with self.lock:
            return self.have_pieces.copy()
    
    def reset_piece(self, piece_index: int):
        """
        Reset a piece to be downloaded again.
        
        Args:
            piece_index: Piece index to reset
        """
        with self.lock:
            if piece_index in self.pieces:
                piece = self.pieces[piece_index]
                piece.reset()
                
                # Remove from completed set
                self.completed_pieces.discard(piece_index)
                self.have_pieces[piece_index] = False
                
                # Cancel pending requests for this piece
                stale_requests = [
                    (p, o) for (p, o) in self.pending_requests if p == piece_index
                ]
                for piece_idx, offset in stale_requests:
                    self.cancel_request(piece_idx, offset)
                
                self.logger.info(f"Reset piece {piece_index}")
    
    @property
    def completion_percentage(self) -> float:
        """Get overall completion percentage."""
        with self.lock:
            if self.torrent.num_pieces == 0:
                return 100.0
            return (len(self.completed_pieces) / self.torrent.num_pieces) * 100.0
    
    @property
    def download_rate(self) -> float:
        """Get current download rate in bytes per second."""
        elapsed = time.time() - self.start_time
        return self.bytes_downloaded / elapsed if elapsed > 0 else 0.0
    
    def is_complete(self) -> bool:
        """Check if all pieces have been downloaded and verified."""
        with self.lock:
            return len(self.completed_pieces) >= self.torrent.num_pieces
    
    def __str__(self) -> str:
        """String representation of piece manager."""
        with self.lock:
            completed = len(self.completed_pieces)
            total = self.torrent.num_pieces
            percentage = self.completion_percentage
            
            return (f"PieceManager(pieces={completed}/{total}, "
                    f"completion={percentage:.1f}%, "
                    f"pending={len(self.pending_requests)})")


if __name__ == "__main__":
    # Example usage and testing
    print("BitTorrent Piece Management System")
    print("This module is designed to be used as part of a BitTorrent client.")
    print("Run the main client to see piece management in action.")
