"""
BitTorrent Progress Tracking and Display

This module provides real-time progress tracking and terminal-based
display for BitTorrent downloads, including progress bars, statistics,
and peer information.

Author: BitTorrent CLI Client
"""

import time
import threading
import sys
from typing import Dict, List, Optional
import logging


class ProgressTracker:
    """
    Tracks and displays BitTorrent download progress.
    
    Provides real-time progress information including completion percentage,
    download rates, ETA, and peer statistics.
    """
    
    def __init__(self, torrent, update_interval: float = 1.0):
        """
        Initialize progress tracker.
        
        Args:
            torrent: Torrent object
            update_interval: Progress update interval in seconds
        """
        self.torrent = torrent
        self.update_interval = update_interval
        
        # Progress data
        self.start_time = time.time()
        self.last_update = 0
        self.bytes_downloaded = 0
        self.bytes_uploaded = 0
        self.download_rate = 0.0
        self.upload_rate = 0.0
        self.eta = 0
        
        # Piece tracking
        self.pieces_completed = 0
        self.total_pieces = torrent.num_pieces
        
        # Peer tracking
        self.connected_peers = 0
        self.total_peers_seen = 0
        
        # Rate calculation
        self.rate_samples = []
        self.max_samples = 10
        
        # Display state
        self.running = False
        self.display_thread = None
        self.last_line_length = 0
        
        # Setup logging
        self.logger = logging.getLogger("ProgressTracker")
    
    def start(self):
        """Start progress tracking and display."""
        self.running = True
        self.start_time = time.time()
        
        self.display_thread = threading.Thread(target=self._display_loop, daemon=True)
        self.display_thread.start()
        
        self.logger.debug("Progress tracking started")
    
    def stop(self):
        """Stop progress tracking and display."""
        self.running = False
        
        if self.display_thread and self.display_thread.is_alive():
            self.display_thread.join(timeout=1.0)
        
        # Clear progress line
        if self.last_line_length > 0:
            sys.stdout.write('\r' + ' ' * self.last_line_length + '\r')
            sys.stdout.flush()
        
        self.logger.debug("Progress tracking stopped")
    
    def update(self, piece_manager, peer_manager=None):
        """
        Update progress information.
        
        Args:
            piece_manager: PieceManager instance
            peer_manager: Optional PeerManager instance
        """
        current_time = time.time()
        
        # Get progress from piece manager
        progress = piece_manager.get_progress()
        
        self.pieces_completed = progress['pieces_completed']
        self.bytes_downloaded = progress['bytes_completed']
        
        # Calculate download rate
        if self.last_update > 0:
            time_delta = current_time - self.last_update
            bytes_delta = self.bytes_downloaded - getattr(self, '_last_bytes', 0)
            
            if time_delta > 0:
                current_rate = bytes_delta / time_delta
                self.rate_samples.append(current_rate)
                
                # Keep only recent samples
                if len(self.rate_samples) > self.max_samples:
                    self.rate_samples.pop(0)
                
                # Calculate average rate
                self.download_rate = sum(self.rate_samples) / len(self.rate_samples)
        
        # Calculate ETA
        if self.download_rate > 0:
            remaining_bytes = self.torrent.total_length - self.bytes_downloaded
            self.eta = remaining_bytes / self.download_rate
        else:
            self.eta = 0
        
        # Update peer information
        if peer_manager:
            self.connected_peers = len(peer_manager.connected_peers)
            self.total_peers_seen = peer_manager.total_peers_seen
        
        self._last_bytes = self.bytes_downloaded
        self.last_update = current_time
    
    def _display_loop(self):
        """Main display loop."""
        while self.running:
            try:
                self._display_progress()
                time.sleep(self.update_interval)
            except Exception as e:
                self.logger.error(f"Display error: {e}")
                break
    
    def _display_progress(self):
        """Display current progress."""
        # Calculate progress percentage
        if self.total_pieces > 0:
            piece_percentage = (self.pieces_completed / self.total_pieces) * 100
        else:
            piece_percentage = 0
        
        if self.torrent.total_length > 0:
            byte_percentage = (self.bytes_downloaded / self.torrent.total_length) * 100
        else:
            byte_percentage = 0
        
        # Create progress bar
        bar_width = 30
        filled_width = int(bar_width * byte_percentage / 100)
        bar = '█' * filled_width + '░' * (bar_width - filled_width)
        
        # Format sizes
        downloaded_mb = self.bytes_downloaded / (1024 * 1024)
        total_mb = self.torrent.total_length / (1024 * 1024)
        
        # Format rate
        if self.download_rate > 1024 * 1024:
            rate_str = f"{self.download_rate / (1024 * 1024):.1f} MB/s"
        elif self.download_rate > 1024:
            rate_str = f"{self.download_rate / 1024:.1f} KB/s"
        else:
            rate_str = f"{self.download_rate:.1f} B/s"
        
        # Format ETA
        if self.eta > 0:
            eta_str = self._format_time(self.eta)
        else:
            eta_str = "∞"
        
        # Build progress line
        progress_line = (
            f"Progress: |{bar}| {byte_percentage:5.1f}% "
            f"({self.pieces_completed}/{self.total_pieces} pieces)\n"
            f"Size:     {downloaded_mb:8.1f} / {total_mb:.1f} MB\n"
            f"Speed:    ↓ {rate_str:>10} | ETA: {eta_str:>8}\n"
            f"Peers:    {self.connected_peers} connected | {self.total_peers_seen} total seen"
        )
        
        # Clear previous output
        if self.last_line_length > 0:
            lines_to_clear = 4  # Number of lines in our display
            sys.stdout.write('\033[F' * lines_to_clear)  # Move cursor up
            sys.stdout.write('\033[J')  # Clear from cursor to end of screen
        
        # Display progress
        sys.stdout.write(progress_line)
        sys.stdout.flush()
        
        self.last_line_length = len(progress_line)
    
    def _format_time(self, seconds: float) -> str:
        """
        Format time duration in human-readable format.
        
        Args:
            seconds: Time in seconds
            
        Returns:
            Formatted time string
        """
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs:02d}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes:02d}m"
    
    def print_summary(self):
        """Print final download summary."""
        elapsed = time.time() - self.start_time
        avg_rate = self.bytes_downloaded / elapsed if elapsed > 0 else 0
        
        if avg_rate > 1024 * 1024:
            avg_rate_str = f"{avg_rate / (1024 * 1024):.2f} MB/s"
        elif avg_rate > 1024:
            avg_rate_str = f"{avg_rate / 1024:.2f} KB/s"
        else:
            avg_rate_str = f"{avg_rate:.2f} B/s"
        
        print(f"\n{'='*60}")
        print(f"Download Complete!")
        print(f"{'='*60}")
        print(f"Total Size:     {self.torrent.total_length / (1024*1024):.2f} MB")
        print(f"Time Elapsed:   {self._format_time(elapsed)}")
        print(f"Average Speed:  {avg_rate_str}")
        print(f"Pieces:         {self.pieces_completed}/{self.total_pieces}")
        print(f"Peers Used:     {self.total_peers_seen}")
        print(f"{'='*60}")
    
    @property
    def completion_percentage(self) -> float:
        """Get completion percentage."""
        if self.torrent.total_length > 0:
            return (self.bytes_downloaded / self.torrent.total_length) * 100
        return 0.0
    
    @property
    def is_complete(self) -> bool:
        """Check if download is complete."""
        return self.pieces_completed >= self.total_pieces


class PeerTracker:
    """Tracks peer statistics and connections."""
    
    def __init__(self):
        """Initialize peer tracker."""
        self.connected_peers = {}
        self.total_peers_seen = 0
        self.max_peers = 0
        
        # Statistics
        self.total_downloaded = 0
        self.total_uploaded = 0
        
        # Threading
        self.lock = threading.RLock()
    
    def add_peer(self, peer_id: str, peer_info: Dict):
        """
        Add a peer to tracking.
        
        Args:
            peer_id: Unique peer identifier
            peer_info: Peer information dictionary
        """
        with self.lock:
            if peer_id not in self.connected_peers:
                self.total_peers_seen += 1
            
            self.connected_peers[peer_id] = {
                'connect_time': time.time(),
                'bytes_downloaded': 0,
                'bytes_uploaded': 0,
                **peer_info
            }
            
            self.max_peers = max(self.max_peers, len(self.connected_peers))
    
    def remove_peer(self, peer_id: str):
        """
        Remove a peer from tracking.
        
        Args:
            peer_id: Peer identifier to remove
        """
        with self.lock:
            if peer_id in self.connected_peers:
                peer_info = self.connected_peers[peer_id]
                self.total_downloaded += peer_info.get('bytes_downloaded', 0)
                self.total_uploaded += peer_info.get('bytes_uploaded', 0)
                
                del self.connected_peers[peer_id]
    
    def update_peer_stats(self, peer_id: str, downloaded: int, uploaded: int):
        """
        Update peer transfer statistics.
        
        Args:
            peer_id: Peer identifier
            downloaded: Bytes downloaded from this peer
            uploaded: Bytes uploaded to this peer
        """
        with self.lock:
            if peer_id in self.connected_peers:
                self.connected_peers[peer_id]['bytes_downloaded'] = downloaded
                self.connected_peers[peer_id]['bytes_uploaded'] = uploaded
    
    def get_peer_stats(self) -> Dict:
        """
        Get comprehensive peer statistics.
        
        Returns:
            Dictionary containing peer statistics
        """
        with self.lock:
            active_peers = len(self.connected_peers)
            
            # Calculate rates
            total_down = sum(p.get('bytes_downloaded', 0) for p in self.connected_peers.values())
            total_up = sum(p.get('bytes_uploaded', 0) for p in self.connected_peers.values())
            
            return {
                'active_peers': active_peers,
                'total_peers_seen': self.total_peers_seen,
                'max_concurrent': self.max_peers,
                'total_downloaded': self.total_downloaded + total_down,
                'total_uploaded': self.total_uploaded + total_up
            }


class FileProgressTracker:
    """Tracks progress for individual files in multi-file torrents."""
    
    def __init__(self, torrent):
        """
        Initialize file progress tracker.
        
        Args:
            torrent: Torrent object
        """
        self.torrent = torrent
        self.file_progress = {}
        
        # Initialize file tracking
        for i, torrent_file in enumerate(torrent.files):
            self.file_progress[i] = {
                'name': torrent_file.full_path,
                'size': torrent_file.length,
                'downloaded': 0,
                'complete': False
            }
    
    def update_file_progress(self, piece_manager):
        """
        Update file progress based on completed pieces.
        
        Args:
            piece_manager: PieceManager instance
        """
        # This is a simplified implementation
        # A full implementation would map pieces to files precisely
        
        total_downloaded = piece_manager.bytes_downloaded
        total_size = self.torrent.total_length
        
        if total_size > 0:
            overall_progress = total_downloaded / total_size
            
            # Distribute progress across files proportionally
            for file_id, file_info in self.file_progress.items():
                file_downloaded = int(file_info['size'] * overall_progress)
                file_info['downloaded'] = min(file_downloaded, file_info['size'])
                file_info['complete'] = file_info['downloaded'] >= file_info['size']
    
    def get_file_status(self) -> List[Dict]:
        """
        Get status of all files.
        
        Returns:
            List of file status dictionaries
        """
        return list(self.file_progress.values())
    
    def print_file_status(self):
        """Print detailed file status."""
        print(f"\nFile Progress:")
        print(f"{'='*80}")
        
        for file_info in self.file_progress.values():
            name = file_info['name']
            size_mb = file_info['size'] / (1024 * 1024)
            downloaded_mb = file_info['downloaded'] / (1024 * 1024)
            
            if file_info['size'] > 0:
                percentage = (file_info['downloaded'] / file_info['size']) * 100
            else:
                percentage = 100
            
            status = "✓" if file_info['complete'] else "⏳"
            
            # Truncate long filenames
            if len(name) > 50:
                display_name = name[:47] + "..."
            else:
                display_name = name.ljust(50)
            
            print(f"{status} {display_name} {percentage:6.1f}% "
                  f"({downloaded_mb:6.1f}/{size_mb:6.1f} MB)")


if __name__ == "__main__":
    # Example usage and testing
    print("BitTorrent Progress Tracking System")
    print("This module is designed to be used as part of a BitTorrent client.")
    print("Run the main client to see progress tracking in action.")
