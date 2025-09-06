#!/usr/bin/env python3
"""
BitTorrent Progress Tracking and Display

This module provides real-time progress tracking and terminal-based
progress display for BitTorrent downloads.
"""

import time
import threading
import sys
import os
from typing import Dict, List, Optional, Callable
from collections import deque
import logging


class ProgressTracker:
    """Tracks download progress and statistics."""
    
    def __init__(self, total_size: int, total_pieces: int):
        self.total_size = total_size
        self.total_pieces = total_pieces
        
        # Progress tracking
        self.downloaded_bytes = 0
        self.uploaded_bytes = 0
        self.completed_pieces = 0
        self.start_time = time.time()
        
        # Speed calculation
        self.speed_samples = deque(maxlen=30)  # Last 30 seconds
        self.upload_speed_samples = deque(maxlen=30)
        self.last_update_time = time.time()
        self.last_downloaded = 0
        self.last_uploaded = 0
        
        # Peer tracking
        self.active_peers = 0
        self.total_peers_seen = 0
        
        # Thread safety
        self.lock = threading.RLock()
        
        self.logger = logging.getLogger(__name__)
    
    def update_progress(self, downloaded_bytes: int, uploaded_bytes: int, 
                       completed_pieces: int, active_peers: int):
        """Update progress statistics."""
        with self.lock:
            current_time = time.time()
            
            # Calculate speed since last update
            time_diff = current_time - self.last_update_time
            if time_diff >= 1.0:  # Update speed every second
                download_speed = (downloaded_bytes - self.last_downloaded) / time_diff
                upload_speed = (uploaded_bytes - self.last_uploaded) / time_diff
                
                self.speed_samples.append((current_time, download_speed))
                self.upload_speed_samples.append((current_time, upload_speed))
                
                self.last_update_time = current_time
                self.last_downloaded = downloaded_bytes
                self.last_uploaded = uploaded_bytes
            
            self.downloaded_bytes = downloaded_bytes
            self.uploaded_bytes = uploaded_bytes
            self.completed_pieces = completed_pieces
            self.active_peers = active_peers
            
            if active_peers > self.total_peers_seen:
                self.total_peers_seen = active_peers
    
    def get_completion_percentage(self) -> float:
        """Get completion percentage."""
        with self.lock:
            if self.total_size == 0:
                return 0.0
            return (self.downloaded_bytes / self.total_size) * 100
    
    def get_piece_completion_percentage(self) -> float:
        """Get piece completion percentage."""
        with self.lock:
            if self.total_pieces == 0:
                return 0.0
            return (self.completed_pieces / self.total_pieces) * 100
    
    def get_download_speed(self) -> float:
        """Get current download speed in bytes per second."""
        with self.lock:
            if not self.speed_samples:
                return 0.0
            
            current_time = time.time()
            # Average speed over last 10 seconds
            recent_samples = [(t, s) for t, s in self.speed_samples if current_time - t <= 10]
            
            if not recent_samples:
                return 0.0
            
            return sum(speed for _, speed in recent_samples) / len(recent_samples)
    
    def get_upload_speed(self) -> float:
        """Get current upload speed in bytes per second."""
        with self.lock:
            if not self.upload_speed_samples:
                return 0.0
            
            current_time = time.time()
            recent_samples = [(t, s) for t, s in self.upload_speed_samples if current_time - t <= 10]
            
            if not recent_samples:
                return 0.0
            
            return sum(speed for _, speed in recent_samples) / len(recent_samples)
    
    def get_average_speed(self) -> float:
        """Get average download speed since start."""
        with self.lock:
            elapsed = time.time() - self.start_time
            if elapsed == 0:
                return 0.0
            return self.downloaded_bytes / elapsed
    
    def get_eta(self) -> Optional[float]:
        """Get estimated time to completion in seconds."""
        with self.lock:
            remaining_bytes = self.total_size - self.downloaded_bytes
            if remaining_bytes <= 0:
                return 0.0
            
            current_speed = self.get_download_speed()
            if current_speed == 0:
                return None
            
            return remaining_bytes / current_speed
    
    def get_elapsed_time(self) -> float:
        """Get elapsed time since start."""
        return time.time() - self.start_time
    
    def get_statistics(self) -> Dict:
        """Get comprehensive statistics."""
        with self.lock:
            return {
                'total_size': self.total_size,
                'downloaded_bytes': self.downloaded_bytes,
                'uploaded_bytes': self.uploaded_bytes,
                'completion_percentage': self.get_completion_percentage(),
                'piece_completion_percentage': self.get_piece_completion_percentage(),
                'completed_pieces': self.completed_pieces,
                'total_pieces': self.total_pieces,
                'download_speed': self.get_download_speed(),
                'upload_speed': self.get_upload_speed(),
                'average_speed': self.get_average_speed(),
                'eta': self.get_eta(),
                'elapsed_time': self.get_elapsed_time(),
                'active_peers': self.active_peers,
                'total_peers_seen': self.total_peers_seen
            }


class ProgressDisplay:
    """Terminal-based progress display."""
    
    def __init__(self, torrent_name: str, tracker: ProgressTracker, 
                 update_interval: float = 1.0, verbose: bool = False):
        self.torrent_name = torrent_name
        self.tracker = tracker
        self.update_interval = update_interval
        self.verbose = verbose
        
        self.running = False
        self.display_thread = None
        self.logger = logging.getLogger(__name__)
        
        # Terminal info
        self.terminal_width = self._get_terminal_width()
    
    def _get_terminal_width(self) -> int:
        """Get terminal width for progress bar sizing."""
        try:
            return os.get_terminal_size().columns
        except:
            return 80  # Default width
    
    def _format_bytes(self, bytes_value: float) -> str:
        """Format bytes with appropriate unit."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                if unit == 'B':
                    return f"{int(bytes_value)} {unit}"
                else:
                    return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f} PB"
    
    def _format_speed(self, speed: float) -> str:
        """Format speed with appropriate unit."""
        return f"{self._format_bytes(speed)}/s"
    
    def _format_time(self, seconds: Optional[float]) -> str:
        """Format time duration."""
        if seconds is None:
            return "∞"
        
        if seconds < 0:
            return "0s"
        
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
    
    def _create_progress_bar(self, percentage: float, width: int = 40) -> str:
        """Create ASCII progress bar."""
        filled = int(width * percentage / 100)
        bar = '█' * filled + '░' * (width - filled)
        return f"|{bar}|"
    
    def _display_progress(self):
        """Main display loop."""
        while self.running:
            try:
                stats = self.tracker.get_statistics()
                self._print_progress(stats)
                time.sleep(self.update_interval)
            except Exception as e:
                if self.verbose:
                    self.logger.error(f"Display error: {e}")
    
    def _print_progress(self, stats: Dict):
        """Print progress information."""
        # Clear previous lines
        if not self.verbose:
            print("\033[2J\033[H", end="")  # Clear screen and move cursor to top
        
        # Header
        print("BitTorrent CLI Client")
        print("=" * 20)
        print(f"Torrent: {self.torrent_name}")
        print()
        
        # Progress bar
        percentage = stats['completion_percentage']
        bar_width = min(50, self.terminal_width - 20)
        progress_bar = self._create_progress_bar(percentage, bar_width)
        
        print(f"Progress: {progress_bar} {percentage:.2f}% "
              f"({stats['completed_pieces']}/{stats['total_pieces']} pieces)")
        
        # Size information
        downloaded = self._format_bytes(stats['downloaded_bytes'])
        total = self._format_bytes(stats['total_size'])
        print(f"Size:     {downloaded} / {total}")
        
        # Speed information
        current_speed = self._format_speed(stats['download_speed'])
        avg_speed = self._format_speed(stats['average_speed'])
        eta = self._format_time(stats['eta'])
        print(f"Speed:    ↓ {current_speed} | Avg: {avg_speed} | ETA: {eta}")
        
        # Upload information
        if stats['uploaded_bytes'] > 0:
            uploaded = self._format_bytes(stats['uploaded_bytes'])
            upload_speed = self._format_speed(stats['upload_speed'])
            print(f"Upload:   ↑ {upload_speed} | Total: {uploaded}")
        
        # Peer information
        print(f"Peers:    {stats['active_peers']} connected | "
              f"{stats['total_peers_seen']} total seen")
        
        # Time information
        elapsed = self._format_time(stats['elapsed_time'])
        print(f"Time:     {elapsed} elapsed")
        
        if self.verbose:
            print()  # Add newline for verbose mode
        
        sys.stdout.flush()
    
    def start(self):
        """Start progress display."""
        if self.running:
            return
        
        self.running = True
        self.display_thread = threading.Thread(target=self._display_progress, daemon=True)
        self.display_thread.start()
        self.logger.info("Progress display started")
    
    def stop(self):
        """Stop progress display."""
        self.running = False
        if self.display_thread and self.display_thread.is_alive():
            self.display_thread.join(timeout=2)
        self.logger.info("Progress display stopped")
    
    def print_final_summary(self):
        """Print final download summary."""
        stats = self.tracker.get_statistics()
        
        print("\n" + "=" * 50)
        print("DOWNLOAD COMPLETE!")
        print("=" * 50)
        print(f"Torrent:        {self.torrent_name}")
        print(f"Total Size:     {self._format_bytes(stats['total_size'])}")
        print(f"Downloaded:     {self._format_bytes(stats['downloaded_bytes'])}")
        print(f"Uploaded:       {self._format_bytes(stats['uploaded_bytes'])}")
        print(f"Average Speed:  {self._format_speed(stats['average_speed'])}")
        print(f"Total Time:     {self._format_time(stats['elapsed_time'])}")
        print(f"Pieces:         {stats['completed_pieces']}/{stats['total_pieces']}")
        print(f"Peers Used:     {stats['total_peers_seen']}")
        print("=" * 50)


class FileProgressTracker:
    """Track progress for individual files in multi-file torrents."""
    
    def __init__(self, files: List[Dict]):
        self.files = files  # List of file info dicts
        self.file_progress = {i: 0 for i in range(len(files))}
        self.lock = threading.RLock()
    
    def update_file_progress(self, file_index: int, bytes_written: int):
        """Update progress for a specific file."""
        with self.lock:
            if file_index in self.file_progress:
                self.file_progress[file_index] += bytes_written
    
    def get_file_progress(self, file_index: int) -> float:
        """Get progress percentage for a specific file."""
        with self.lock:
            if file_index >= len(self.files):
                return 0.0
            
            file_size = self.files[file_index]['length']
            downloaded = self.file_progress.get(file_index, 0)
            
            if file_size == 0:
                return 100.0
            
            return min(100.0, (downloaded / file_size) * 100)
    
    def get_completed_files(self) -> List[int]:
        """Get list of completed file indices."""
        with self.lock:
            completed = []
            for file_index in range(len(self.files)):
                if self.get_file_progress(file_index) >= 100.0:
                    completed.append(file_index)
            return completed
    
    def print_file_status(self, max_files: int = 10):
        """Print status of files."""
        with self.lock:
            print(f"\nFile Progress (showing {min(max_files, len(self.files))} files):")
            print("-" * 60)
            
            for i in range(min(max_files, len(self.files))):
                file_info = self.files[i]
                progress = self.get_file_progress(i)
                status = "✓" if progress >= 100.0 else "○"
                
                file_name = os.path.basename(file_info['path'])
                if len(file_name) > 30:
                    file_name = file_name[:27] + "..."
                
                print(f"{status} {file_name:<30} {progress:6.1f}%")
            
            if len(self.files) > max_files:
                remaining = len(self.files) - max_files
                completed_remaining = len([i for i in range(max_files, len(self.files)) 
                                         if self.get_file_progress(i) >= 100.0])
                print(f"... and {remaining} more files ({completed_remaining} completed)")


if __name__ == "__main__":
    # Test progress tracking functionality
    import random
    
    print("Testing Progress Tracker...")
    
    # Create tracker for a 100MB torrent with 400 pieces
    total_size = 100 * 1024 * 1024  # 100MB
    total_pieces = 400
    
    tracker = ProgressTracker(total_size, total_pieces)
    display = ProgressDisplay("test.torrent", tracker, update_interval=0.5, verbose=True)
    
    try:
        display.start()
        
        # Simulate download progress
        for i in range(100):
            # Simulate some download progress
            downloaded = int((i / 100) * total_size)
            uploaded = int(downloaded * 0.1)  # 10% upload ratio
            completed_pieces = int((i / 100) * total_pieces)
            active_peers = random.randint(5, 20)
            
            tracker.update_progress(downloaded, uploaded, completed_pieces, active_peers)
            
            time.sleep(0.1)  # Simulate time passing
        
        # Complete the download
        tracker.update_progress(total_size, total_size // 10, total_pieces, 15)
        time.sleep(2)
        
        display.stop()
        display.print_final_summary()
        
    except KeyboardInterrupt:
        display.stop()
        print("\nProgress test interrupted")
    
    print("Progress tracker test completed")
