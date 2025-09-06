#!/usr/bin/env python3
"""
BitTorrent Piece Manager

This module handles piece downloading, verification, and coordination
across multiple peers.
"""

import hashlib
import threading
import time
import logging
from typing import Dict, List, Optional, Set, Tuple, Callable
from enum import Enum
import random


class PieceState(Enum):
    """States of a piece download."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


class Block:
    """Represents a block within a piece."""
    
    def __init__(self, piece_index: int, offset: int, length: int):
        self.piece_index = piece_index
        self.offset = offset
        self.length = length
        self.data = None
        self.requested = False
        self.received = False
        self.request_time = None
        self.peer_ip = None
        self.peer_port = None
    
    def __eq__(self, other):
        return (self.piece_index == other.piece_index and 
                self.offset == other.offset and 
                self.length == other.length)
    
    def __hash__(self):
        return hash((self.piece_index, self.offset, self.length))


class Piece:
    """Represents a piece with its blocks."""
    
    BLOCK_SIZE = 16384  # 16KB standard block size
    
    def __init__(self, index: int, size: int, hash_value: bytes):
        self.index = index
        self.size = size
        self.hash_value = hash_value
        self.state = PieceState.PENDING
        self.blocks = self._create_blocks()
        self.data = bytearray(size)
        self.downloaded_blocks = 0
        self.last_activity = time.time()
        self.download_start_time = None
        self.completion_time = None
        self.peers_tried = set()
    
    def _create_blocks(self) -> List[Block]:
        """Create blocks for this piece."""
        blocks = []
        offset = 0
        
        while offset < self.size:
            block_size = min(self.BLOCK_SIZE, self.size - offset)
            blocks.append(Block(self.index, offset, block_size))
            offset += block_size
        
        return blocks
    
    def get_pending_blocks(self) -> List[Block]:
        """Get blocks that haven't been requested yet."""
        return [block for block in self.blocks if not block.requested and not block.received]
    
    def get_requested_blocks(self) -> List[Block]:
        """Get blocks that have been requested but not received."""
        return [block for block in self.blocks if block.requested and not block.received]
    
    def get_expired_blocks(self, timeout: int = 30) -> List[Block]:
        """Get blocks whose requests have timed out."""
        current_time = time.time()
        expired = []
        
        for block in self.get_requested_blocks():
            if block.request_time and current_time - block.request_time > timeout:
                expired.append(block)
        
        return expired
    
    def mark_block_requested(self, block: Block, peer_ip: str, peer_port: int):
        """Mark a block as requested."""
        block.requested = True
        block.request_time = time.time()
        block.peer_ip = peer_ip
        block.peer_port = peer_port
        self.last_activity = time.time()
        
        if self.state == PieceState.PENDING:
            self.state = PieceState.DOWNLOADING
            self.download_start_time = time.time()
    
    def add_block_data(self, offset: int, data: bytes) -> bool:
        """Add data for a block."""
        # Find the block
        block = None
        for b in self.blocks:
            if b.offset == offset and len(data) == b.length:
                block = b
                break
        
        if not block:
            return False
        
        # Add data to piece
        self.data[offset:offset + len(data)] = data
        block.data = data
        block.received = True
        self.downloaded_blocks += 1
        self.last_activity = time.time()
        
        # Check if piece is complete
        if self.downloaded_blocks == len(self.blocks):
            return self._verify_piece()
        
        return True
    
    def _verify_piece(self) -> bool:
        """Verify piece integrity using SHA1 hash."""
        calculated_hash = hashlib.sha1(self.data).digest()
        
        if calculated_hash == self.hash_value:
            self.state = PieceState.COMPLETED
            self.completion_time = time.time()
            return True
        else:
            # Reset piece for re-download
            self.state = PieceState.FAILED
            self._reset_blocks()
            return False
    
    def _reset_blocks(self):
        """Reset all blocks for re-download."""
        for block in self.blocks:
            block.requested = False
            block.received = False
            block.data = None
            block.request_time = None
            block.peer_ip = None
            block.peer_port = None
        
        self.downloaded_blocks = 0
        self.data = bytearray(self.size)
    
    def reset_expired_blocks(self, timeout: int = 30):
        """Reset blocks that have timed out."""
        expired_blocks = self.get_expired_blocks(timeout)
        for block in expired_blocks:
            block.requested = False
            block.request_time = None
            block.peer_ip = None
            block.peer_port = None
    
    def is_complete(self) -> bool:
        """Check if piece is complete and verified."""
        return self.state == PieceState.COMPLETED
    
    def get_progress(self) -> float:
        """Get download progress as percentage."""
        return (self.downloaded_blocks / len(self.blocks)) * 100
    
    def get_download_time(self) -> Optional[float]:
        """Get time taken to download piece."""
        if self.download_start_time and self.completion_time:
            return self.completion_time - self.download_start_time
        return None


class PieceManager:
    """Manages piece downloading and coordination."""
    
    def __init__(self, torrent_info, piece_completion_callback: Optional[Callable] = None):
        """
        Initialize piece manager.
        
        Args:
            torrent_info: TorrentFile object with torrent metadata
            piece_completion_callback: Called when a piece is completed
        """
        self.torrent_info = torrent_info
        self.piece_completion_callback = piece_completion_callback
        self.pieces = self._create_pieces()
        self.completed_pieces = set()
        self.failed_pieces = set()
        
        self.lock = threading.RLock()
        self.logger = logging.getLogger(__name__)
        
        # Statistics
        self.total_downloaded = 0
        self.download_start_time = time.time()
        self.pieces_completed = 0
        
        # Strategy settings
        self.max_requests_per_peer = 5
        self.block_timeout = 30
        self.rarest_first = True
    
    def _create_pieces(self) -> Dict[int, Piece]:
        """Create piece objects for all pieces in torrent."""
        pieces = {}
        
        for i in range(self.torrent_info.num_pieces):
            piece_size = self.torrent_info.get_piece_size(i)
            piece_hash = self.torrent_info.get_piece_hash(i)
            pieces[i] = Piece(i, piece_size, piece_hash)
        
        return pieces
    
    def mark_piece_complete(self, piece_index: int) -> bool:
        """Mark a piece as already completed (for resume functionality)."""
        with self.lock:
            if piece_index in self.pieces:
                piece = self.pieces[piece_index]
                piece.state = PieceState.COMPLETED
                self.completed_pieces.add(piece_index)
                self.pieces_completed += 1
                self.total_downloaded += piece.size
                return True
            return False
    
    def get_piece_to_download(self, available_pieces: Set[int], peer_ip: str = None, peer_port: int = None) -> Optional[Tuple[int, int, int]]:
        """
        Get next block to download using piece selection strategy.
        
        Args:
            available_pieces: Set of piece indices available from peer
            peer_ip: Peer IP for tracking
            peer_port: Peer port for tracking
            
        Returns:
            Tuple of (piece_index, block_offset, block_length) or None
        """
        with self.lock:
            # Filter available pieces to only those we need
            needed_pieces = available_pieces - self.completed_pieces
            
            if not needed_pieces:
                return None
            
            # Get piece to work on
            piece_index = self._select_piece(needed_pieces, peer_ip, peer_port)
            if piece_index is None:
                return None
            
            piece = self.pieces[piece_index]
            
            # Reset expired blocks
            piece.reset_expired_blocks(self.block_timeout)
            
            # Get next block to download
            pending_blocks = piece.get_pending_blocks()
            if not pending_blocks:
                return None
            
            block = pending_blocks[0]
            piece.mark_block_requested(block, peer_ip or "unknown", peer_port or 0)
            
            return (piece_index, block.offset, block.length)
    
    def _select_piece(self, available_pieces: Set[int], peer_ip: str = None, peer_port: int = None) -> Optional[int]:
        """Select piece using download strategy."""
        # Strategy 1: Continue downloading pieces that are already in progress
        in_progress = []
        for piece_index in available_pieces:
            piece = self.pieces[piece_index]
            if piece.state == PieceState.DOWNLOADING and piece.get_pending_blocks():
                in_progress.append(piece_index)
        
        if in_progress:
            return random.choice(in_progress)
        
        # Strategy 2: Rarest first (simplified)
        if self.rarest_first:
            # For simplicity, just pick randomly from available pieces
            # A real implementation would track piece availability across peers
            pending = [i for i in available_pieces if self.pieces[i].state == PieceState.PENDING]
            if pending:
                return random.choice(pending)
        
        # Strategy 3: Sequential (fallback)
        for piece_index in sorted(available_pieces):
            if self.pieces[piece_index].state == PieceState.PENDING:
                return piece_index
        
        return None
    
    def add_block(self, piece_index: int, block_offset: int, block_data: bytes) -> bool:
        """
        Add block data to a piece.
        
        Args:
            piece_index: Index of the piece
            block_offset: Offset within the piece
            block_data: Block data
            
        Returns:
            True if block was added successfully
        """
        with self.lock:
            if piece_index not in self.pieces:
                return False
            
            piece = self.pieces[piece_index]
            
            if piece.is_complete():
                return True  # Already complete
            
            success = piece.add_block_data(block_offset, block_data)
            
            if success:
                self.total_downloaded += len(block_data)
                
                # Check if piece is now complete
                if piece.is_complete():
                    self.completed_pieces.add(piece_index)
                    self.pieces_completed += 1
                    self.logger.info(f"Piece {piece_index} completed ({self.get_completion_percentage():.1f}%)")
                    
                    if self.piece_completion_callback:
                        self.piece_completion_callback(piece_index, piece.data)
                
                elif piece.state == PieceState.FAILED:
                    self.failed_pieces.add(piece_index)
                    self.logger.warning(f"Piece {piece_index} failed verification, will retry")
                    
                    # Reset piece state for retry
                    piece.state = PieceState.PENDING
                    self.failed_pieces.discard(piece_index)
            
            return success
    
    def get_bitfield(self) -> bytes:
        """Get bitfield of completed pieces."""
        with self.lock:
            # Create bitfield with 1 bit per piece
            bitfield_size = (self.torrent_info.num_pieces + 7) // 8
            bitfield = bytearray(bitfield_size)
            
            for piece_index in self.completed_pieces:
                byte_index = piece_index // 8
                bit_index = 7 - (piece_index % 8)
                bitfield[byte_index] |= (1 << bit_index)
            
            return bytes(bitfield)
    
    def get_completion_percentage(self) -> float:
        """Get overall completion percentage."""
        with self.lock:
            return (len(self.completed_pieces) / self.torrent_info.num_pieces) * 100
    
    def get_downloaded_bytes(self) -> int:
        """Get total bytes downloaded."""
        with self.lock:
            return self.total_downloaded
    
    def get_remaining_bytes(self) -> int:
        """Get bytes remaining to download."""
        with self.lock:
            return self.torrent_info.total_size - self.total_downloaded
    
    def get_download_speed(self) -> float:
        """Get average download speed in bytes per second."""
        with self.lock:
            elapsed = time.time() - self.download_start_time
            if elapsed == 0:
                return 0.0
            return self.total_downloaded / elapsed
    
    def get_piece_status(self) -> Dict:
        """Get detailed piece status information."""
        with self.lock:
            completed = len(self.completed_pieces)
            downloading = len([p for p in self.pieces.values() if p.state == PieceState.DOWNLOADING])
            pending = len([p for p in self.pieces.values() if p.state == PieceState.PENDING])
            failed = len(self.failed_pieces)
            
            return {
                'total_pieces': self.torrent_info.num_pieces,
                'completed': completed,
                'downloading': downloading,
                'pending': pending,
                'failed': failed,
                'completion_percentage': self.get_completion_percentage()
            }
    
    def get_active_downloads(self) -> List[Dict]:
        """Get information about currently downloading pieces."""
        with self.lock:
            active = []
            
            for piece in self.pieces.values():
                if piece.state == PieceState.DOWNLOADING:
                    active.append({
                        'piece_index': piece.index,
                        'progress': piece.get_progress(),
                        'blocks_total': len(piece.blocks),
                        'blocks_downloaded': piece.downloaded_blocks,
                        'blocks_requested': len(piece.get_requested_blocks()),
                        'blocks_pending': len(piece.get_pending_blocks()),
                        'last_activity': piece.last_activity
                    })
            
            return active
    
    def cleanup_expired_requests(self):
        """Clean up expired block requests."""
        with self.lock:
            for piece in self.pieces.values():
                if piece.state == PieceState.DOWNLOADING:
                    piece.reset_expired_blocks(self.block_timeout)
                    
                    # If no blocks are being downloaded, reset piece to pending
                    if not piece.get_requested_blocks() and piece.downloaded_blocks == 0:
                        piece.state = PieceState.PENDING
    
    def is_complete(self) -> bool:
        """Check if all pieces are downloaded."""
        with self.lock:
            return len(self.completed_pieces) == self.torrent_info.num_pieces
    
    def get_next_pieces_for_peer(self, available_pieces: Set[int], max_pieces: int = 5) -> List[Tuple[int, int, int]]:
        """
        Get multiple blocks for a peer to request.
        
        Args:
            available_pieces: Pieces available from this peer
            max_pieces: Maximum number of blocks to return
            
        Returns:
            List of (piece_index, block_offset, block_length) tuples
        """
        requests = []
        
        for _ in range(max_pieces):
            request = self.get_piece_to_download(available_pieces)
            if request:
                requests.append(request)
            else:
                break
        
        return requests
    
    def cancel_peer_requests(self, peer_ip: str, peer_port: int):
        """Cancel all pending requests from a specific peer."""
        with self.lock:
            for piece in self.pieces.values():
                for block in piece.blocks:
                    if (block.requested and not block.received and 
                        block.peer_ip == peer_ip and block.peer_port == peer_port):
                        block.requested = False
                        block.request_time = None
                        block.peer_ip = None
                        block.peer_port = None


if __name__ == "__main__":
    # Test piece manager functionality
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python piece_manager_client.py <torrent_file>")
        sys.exit(1)
    
    logging.basicConfig(level=logging.DEBUG)
    
    from torrent_new import parse_torrent
    
    try:
        torrent = parse_torrent(sys.argv[1])
        
        def piece_completed(piece_index, piece_data):
            print(f"Piece {piece_index} completed! ({len(piece_data)} bytes)")
        
        piece_manager = PieceManager(torrent, piece_completed)
        
        print(f"Torrent: {torrent.name}")
        print(f"Total pieces: {torrent.num_pieces}")
        print(f"Total size: {torrent.total_size:,} bytes")
        
        # Simulate some available pieces
        available_pieces = set(range(min(10, torrent.num_pieces)))
        
        # Get some blocks to download
        for i in range(5):
            request = piece_manager.get_piece_to_download(available_pieces)
            if request:
                piece_index, offset, length = request
                print(f"Request {i+1}: Piece {piece_index}, offset {offset}, length {length}")
            else:
                print(f"No more blocks available")
                break
        
        print(f"\nPiece status: {piece_manager.get_piece_status()}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
