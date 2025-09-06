# piece_manager.py: Manages pieces and blocks in RAM, verifies, and notifies via pubsub.

import hashlib
import time
import os
from pubsub import pub
from bitstring import BitArray
from utils import sha1_hash, BLOCK_SIZE
from progress_manager import save_progress, load_progress

class PieceManager:
    def __init__(self, torrent, file_manager, seed_mode=False):
        """Initialize piece manager."""
        self.torrent = torrent
        self.file_manager = file_manager
        self.pieces = {}  # index -> list of blocks
        self.have_pieces = set()  # For seeding bitfield
        self.failed_pieces = set()  # Track failed pieces for retry
        self.piece_progress = {}  # Track progress per piece
        self.last_piece_request = {}  # Track when pieces were last requested
        self.stalled_threshold = 60  # Seconds before considering a piece stalled
        self.progress_file = os.path.join(self.file_manager.output_path, "progress.json")
        
        # Try to load saved progress
        if not seed_mode:
            saved_progress = load_progress(self.progress_file)
            if saved_progress:
                print("\nFound saved progress, resuming download...")
                self.have_pieces = set(saved_progress.get('have_pieces', []))
                self.piece_progress = saved_progress.get('piece_progress', {})
                # Convert string keys back to integers
                self.piece_progress = {int(k): v for k, v in self.piece_progress.items()}
        # Use the global pub instance
        pub.subscribe(self.on_piece_received, 'piece_received')
        
        if seed_mode:
            print("\nInitializing seed mode...")
            self._verify_all_pieces()

    def has_piece(self, index):
        """Check if piece is complete."""
        return index in self.have_pieces

    def receive_block(self, index, begin, block):
        """Receive a block and check if piece is complete."""
        try:
            # Validate piece index
            if index >= self.torrent.num_pieces:
                print(f"\nError: Invalid piece index {index}")
                return
                
            # Initialize piece tracking if needed
            if index not in self.pieces:
                num_blocks = (self.piece_length(index) + BLOCK_SIZE - 1) // BLOCK_SIZE
                self.pieces[index] = [None] * num_blocks
                self.piece_progress[index] = 0
                print(f"\nInitialized piece {index} tracking ({num_blocks} blocks, {self.piece_length(index)} bytes)")
                
            # Validate block offset
            block_index = begin // BLOCK_SIZE
            if block_index >= len(self.pieces[index]):
                print(f"\nError: Invalid block index {block_index} for piece {index}")
                return
                
            # Validate block size
            expected_size = min(BLOCK_SIZE, self.piece_length(index) - begin)
            if len(block) != expected_size:
                print(f"\nError: Invalid block size {len(block)} != {expected_size}")
                return
                
            # Store the block
            self.pieces[index][block_index] = block
            
            # Calculate completion percentage
            completed_blocks = sum(1 for b in self.pieces[index] if b is not None)
            total_blocks = len(self.pieces[index])
            percent = (completed_blocks / total_blocks) * 100
            
            if completed_blocks == total_blocks:
                print(f"\nPiece {index} complete ({self.piece_length(index)} bytes), verifying...")
                full_piece = b''.join(self.pieces[index])
                
                # Verify piece hash
                piece_hash = sha1_hash(full_piece)
                expected_hash = self.torrent.piece_hashes[index]
                
                if piece_hash == expected_hash:
                    print(f"Piece {index} verified successfully")
                    pub.sendMessage('piece_received', index=index, piece=full_piece)
                    if index in self.failed_pieces:
                        self.failed_pieces.remove(index)
                else:
                    print(f"Piece {index} verification failed!")
                    self.pieces[index] = [None] * total_blocks  # Reset piece for re-download
                    self.failed_pieces.add(index)
                    self.piece_progress[index] = 0
                    
            # Update progress tracking
            prev_progress = self.piece_progress.get(index, 0)
            new_progress = (completed_blocks / total_blocks) * 100
            if new_progress > prev_progress or new_progress - prev_progress >= 5:
                self.piece_progress[index] = new_progress
                print(f"\rPiece {index}: {new_progress:.1f}% ({completed_blocks}/{total_blocks} blocks)", end='')
                
        except Exception as e:
            print(f"\nError receiving block for piece {index}: {str(e)}")
            import traceback
            traceback.print_exc()

    def on_piece_received(self, index, piece):
        """Verify piece and write to disk if valid."""
        expected_hash = self.torrent.piece_hashes[index]
        if sha1_hash(piece) == expected_hash:
            print(f"\nPiece {index} hash verified, writing to disk...")
            self.file_manager.write_piece(index, piece)
            self.have_pieces.add(index)
            self.piece_progress[index] = 100  # Mark as complete
            if index in self.pieces:
                del self.pieces[index]
            if index in self.failed_pieces:
                self.failed_pieces.remove(index)
            pub.sendMessage('piece_verified', index=index)
            print(f"Piece {index} written successfully")
            
            # Save progress after each piece
            progress_data = {
                'have_pieces': list(self.have_pieces),
                'piece_progress': self.piece_progress
            }
            save_progress(self.progress_file, progress_data)
        else:
            print(f"\nPiece {index} failed hash verification, will retry")
            self.failed_pieces.add(index)
            if index in self.pieces:
                del self.pieces[index]  # Clear any partial data
            self.piece_progress[index] = 0  # Reset progress

    def get_block(self, index, begin, length):
        """Read block from disk for seeding."""
        return self.file_manager.read_block(index, begin, length)

    def piece_length(self, index):
        """Get piece length."""
        if index == self.torrent.num_pieces - 1:
            return self.torrent.total_length - index * self.torrent.piece_length
        return self.torrent.piece_length

    def _verify_all_pieces(self):
        """Verify all pieces for seeding."""
        print("\nVerifying all pieces for seeding...")
        try:
            verified_pieces = 0
            total_pieces = self.torrent.num_pieces
            
            for index in range(total_pieces):
                # Read piece data
                piece_data = self.file_manager.read_piece(index)
                if piece_data is None:
                    print(f"[ERROR] Failed to read piece {index}")
                    print("[ERROR] Make sure all files are present and readable")
                    raise ValueError(f"Failed to read piece {index}")
                
                # Calculate and verify hash
                actual_hash = sha1_hash(piece_data)
                expected_hash = self.torrent.piece_hashes[index]
                
                if actual_hash != expected_hash:
                    print(f"[ERROR] Hash mismatch for piece {index}")
                    print(f"Expected: {expected_hash.hex()}")
                    print(f"Got:      {actual_hash.hex()}")
                    raise ValueError(f"Piece {index} hash verification failed")
                
                self.have_pieces.add(index)
                verified_pieces += 1
                
                if verified_pieces % 10 == 0 or verified_pieces == total_pieces:
                    print(f"Verified {verified_pieces}/{total_pieces} pieces")
                    
        except Exception as e:
            print("\n[ERROR] Seeding verification failed")
            print("[ERROR] Make sure all files are available and complete before seeding")
            print(f"[ERROR] Details: {str(e)}")
            raise ValueError("Make sure all files are available and complete before seeding") from e
        
        print(f"\nSuccessfully verified all {verified_pieces} pieces for seeding")

    def get_bitfield(self):
        """Get bitfield for seeding."""
        bitfield = BitArray(length=self.torrent.num_pieces)
        for i in self.have_pieces:
            bitfield[i] = True
        return bitfield

    def get_needed_pieces(self, peer_bitfield):
        """Get list of pieces we need from a peer."""
        needed = []
        for i in range(self.torrent.num_pieces):
            # Skip if we already have it
            if i in self.have_pieces:
                continue
                
            # Skip if peer doesn't have it
            if not peer_bitfield[i]:
                continue
                
            # Skip if we're actively downloading it unless it's stalled
            if i in self.pieces and i not in self.failed_pieces:
                last_request = self.last_piece_request.get(i, 0)
                if time.time() - last_request < self.stalled_threshold:
                    # Check if piece has shown progress recently
                    if i in self.piece_progress and self.piece_progress[i] > 0:
                        continue
                else:
                    # Piece is stalled, reset it
                    print(f"\nPiece {i} appears stalled, marking for retry")
                    self.failed_pieces.add(i)
                    self.pieces[i] = [None] * ((self.piece_length(i) + BLOCK_SIZE - 1) // BLOCK_SIZE)
                    self.piece_progress[i] = 0
                    
            needed.append(i)
        return needed

    def get_download_status(self):
        """Get current download status."""
        total_pieces = self.torrent.num_pieces
        have_count = len(self.have_pieces)
        downloading = len(self.pieces)
        failed = len(self.failed_pieces)
        needed = total_pieces - have_count
        
        # Calculate overall progress including partial pieces
        total_progress = 0
        active_pieces = []
        stalled_pieces = []
        current_time = time.time()
        
        for i in range(total_pieces):
            if i in self.have_pieces:
                total_progress += 100
            elif i in self.piece_progress:
                progress = self.piece_progress[i]
                total_progress += progress
                
                # Track piece status
                if i in self.pieces:
                    last_request = self.last_piece_request.get(i, 0)
                    if current_time - last_request >= self.stalled_threshold:
                        stalled_pieces.append(i)
                    else:
                        active_pieces.append(i)
                
        overall_percent = total_progress / (total_pieces * 100) * 100
        
        return {
            'total_pieces': total_pieces,
            'have_pieces': have_count,
            'downloading': downloading,
            'failed': failed,
            'needed': needed,
            'percent_complete': overall_percent,
            'active_pieces': len(active_pieces),
            'stalled_pieces': len(stalled_pieces),
            'active_piece_numbers': active_pieces,
            'stalled_piece_numbers': stalled_pieces,
            'bytes_downloaded': sum(self.piece_length(i) for i in self.have_pieces),
            'total_bytes': self.torrent.total_length
        }