#!/usr/bin/env python3
"""
Complete BitTorrent Client Implementation

A modular BitTorrent client that implements the full BitTorrent protocol
specification, supporting both single-file and multi-file torrents with
HTTP/HTTPS/UDP tracker support.

Usage:
    python main.py <torrent_file> [options]

Author: BitTorrent CLI Client
"""

import os
import sys
import argparse
import signal
import time
import threading
import logging
from pathlib import Path
from typing import Optional

# Import our complete modules
from torrent_complete import Torrent
from tracker_complete import TrackerManager
from peer_complete import PeerManager
from piece_manager_complete import PieceManager
from file_manager_complete import FileManager
from progress_complete import ProgressTracker, FileProgressTracker


class BitTorrentClient:
    """
    Complete BitTorrent client implementation.
    
    Coordinates all components to download torrents following the
    BitTorrent protocol specification.
    """
    
    def __init__(self, torrent_file: str, download_dir: str = "downloads",
                 max_peers: int = 50, port: int = 6881):
        """
        Initialize BitTorrent client.
        
        Args:
            torrent_file: Path to .torrent file
            download_dir: Directory to save downloaded files
            max_peers: Maximum number of peer connections
            port: Local port for peer connections
        """
        self.torrent_file = torrent_file
        self.download_dir = Path(download_dir)
        self.max_peers = max_peers
        self.port = port
        
        # Core components
        self.torrent: Optional[Torrent] = None
        self.tracker_manager: Optional[TrackerManager] = None
        self.peer_manager: Optional[PeerManager] = None
        self.piece_manager: Optional[PieceManager] = None
        self.file_manager: Optional[FileManager] = None
        self.progress_tracker: Optional[ProgressTracker] = None
        self.file_progress: Optional[FileProgressTracker] = None
        
        # State management
        self.running = False
        self.completed = False
        self.shutdown_event = threading.Event()
        
        # Setup logging
        self.logger = logging.getLogger("BitTorrentClient")
        
        # Generate peer ID (20 bytes, often starts with client identifier)
        import secrets
        self.peer_id = b'-PC0001-' + secrets.token_bytes(12)  # PC for Python Client
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def initialize(self) -> bool:
        """
        Initialize all client components.
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Parse torrent file
            self.logger.info(f"Loading torrent: {self.torrent_file}")
            self.torrent = Torrent(self.torrent_file)
            
            if not self.torrent.info_hash:
                self.logger.error("Failed to parse torrent file")
                return False
            
            self.logger.info(f"Torrent loaded: {self.torrent.name}")
            self.logger.info(f"Info hash: {self.torrent.info_hash.hex()}")
            self.logger.info(f"Total size: {self.torrent.total_length / (1024*1024):.2f} MB")
            self.logger.info(f"Pieces: {len(self.torrent.pieces)}")
            
            # Create download directory
            self.download_dir.mkdir(parents=True, exist_ok=True)
            
            # Initialize file manager
            self.file_manager = FileManager(self.torrent, str(self.download_dir))
            
            # Initialize piece manager
            self.piece_manager = PieceManager(self.torrent, self.file_manager)
            
            # Initialize tracker manager
            self.tracker_manager = TrackerManager(self.torrent, self.peer_id, self.port)
            
            # Initialize peer manager
            self.peer_manager = PeerManager(
                self.torrent, 
                self.piece_manager, 
                self.port,
                max_peers=self.max_peers
            )
            
            # Initialize progress tracking
            self.progress_tracker = ProgressTracker(self.torrent)
            
            if len(self.torrent.files) > 1:
                self.file_progress = FileProgressTracker(self.torrent)
            
            self.logger.info("Client initialization complete")
            return True
            
        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            return False
    
    def start(self) -> bool:
        """
        Start the BitTorrent download.
        
        Returns:
            True if download completed successfully, False otherwise
        """
        if not self.initialize():
            return False
        
        try:
            self.running = True
            self.logger.info("Starting BitTorrent download...")
            
            # Start progress tracking
            self.progress_tracker.start()
            
            # Start peer manager
            self.peer_manager.start()
            
            # Get initial peers from trackers
            self.logger.info("Connecting to trackers...")
            peers = self.tracker_manager.announce(event='started')
            
            if not peers:
                self.logger.warning("No peers found from trackers")
            else:
                self.logger.info(f"Found {len(peers)} peers from trackers")
                
                # Add peers to manager
                for ip, port in peers:
                    self.peer_manager.add_peer(ip, port)
            
            # Main download loop
            return self._download_loop()
            
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            return False
        finally:
            self.stop()
    
    def _download_loop(self) -> bool:
        """
        Main download coordination loop.
        
        Returns:
            True if download completed, False if stopped/failed
        """
        last_tracker_update = 0
        tracker_interval = 300  # 5 minutes
        
        last_progress_update = 0
        progress_interval = 1.0  # 1 second
        
        while self.running and not self.shutdown_event.is_set():
            try:
                current_time = time.time()
                
                # Update progress
                if current_time - last_progress_update >= progress_interval:
                    self.progress_tracker.update(self.piece_manager, self.peer_manager)
                    
                    if self.file_progress:
                        self.file_progress.update_file_progress(self.piece_manager)
                    
                    last_progress_update = current_time
                
                # Check if download is complete
                if self.piece_manager.is_complete():
                    self.logger.info("Download completed!")
                    self.completed = True
                    
                    # Send completion event to trackers
                    self.tracker_manager.announce(event='completed')
                    
                    # Show final summary
                    self.progress_tracker.print_summary()
                    
                    if self.file_progress:
                        self.file_progress.print_file_status()
                    
                    return True
                
                # Periodic tracker updates
                if current_time - last_tracker_update >= tracker_interval:
                    new_peers = self.tracker_manager.announce()
                    
                    if new_peers:
                        self.logger.debug(f"Got {len(new_peers)} peers from tracker update")
                        for ip, port in new_peers:
                            self.peer_manager.add_peer(ip, port)
                    
                    last_tracker_update = current_time
                
                # Check peer manager health
                if len(self.peer_manager.connected_peers) == 0:
                    self.logger.warning("No connected peers, trying to get more from trackers...")
                    new_peers = self.tracker_manager.announce()
                    
                    if new_peers:
                        for ip, port in new_peers:
                            self.peer_manager.add_peer(ip, port)
                
                # Sleep briefly to avoid busy waiting
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                self.logger.info("Download interrupted by user")
                break
            except Exception as e:
                self.logger.error(f"Download loop error: {e}")
                break
        
        return self.completed
    
    def stop(self):
        """Stop the BitTorrent client and cleanup."""
        if not self.running:
            return
        
        self.logger.info("Stopping BitTorrent client...")
        self.running = False
        self.shutdown_event.set()
        
        # Stop components in reverse order
        if self.progress_tracker:
            self.progress_tracker.stop()
        
        if self.peer_manager:
            self.peer_manager.stop()
        
        if self.tracker_manager and not self.completed:
            # Send stopped event to trackers
            try:
                self.tracker_manager.announce(event='stopped')
            except Exception as e:
                self.logger.debug(f"Failed to send stopped event: {e}")
        
        self.logger.info("Client stopped")
    
    def get_status(self) -> dict:
        """
        Get current download status.
        
        Returns:
            Status dictionary with current download information
        """
        if not self.piece_manager or not self.progress_tracker:
            return {"status": "not_initialized"}
        
        progress = self.piece_manager.get_progress()
        
        return {
            "status": "downloading" if self.running else "stopped",
            "completed": self.completed,
            "progress_percentage": self.progress_tracker.completion_percentage,
            "pieces_completed": progress['pieces_completed'],
            "total_pieces": progress['total_pieces'],
            "bytes_downloaded": progress['bytes_completed'],
            "total_bytes": self.torrent.total_length,
            "download_rate": self.progress_tracker.download_rate,
            "connected_peers": len(self.peer_manager.connected_peers) if self.peer_manager else 0,
            "eta": self.progress_tracker.eta
        }


def setup_logging(level: str = "INFO", log_file: Optional[str] = None):
    """
    Setup logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
    """
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    handlers = [logging.StreamHandler(sys.stdout)]
    
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        handlers=handlers
    )


def main():
    """Main entry point for the BitTorrent client."""
    parser = argparse.ArgumentParser(
        description="Complete BitTorrent Client Implementation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py ubuntu.torrent
  python main.py movie.torrent --download-dir ./downloads --max-peers 100
  python main.py file.torrent --port 6882 --log-level DEBUG
        """
    )
    
    parser.add_argument(
        "torrent_file",
        help="Path to the .torrent file to download"
    )
    
    parser.add_argument(
        "--download-dir", "-d",
        default="downloads",
        help="Directory to save downloaded files (default: downloads)"
    )
    
    parser.add_argument(
        "--max-peers", "-p",
        type=int,
        default=50,
        help="Maximum number of peer connections (default: 50)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=6881,
        help="Local port for peer connections (default: 6881)"
    )
    
    parser.add_argument(
        "--log-level", "-l",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    parser.add_argument(
        "--log-file",
        help="Log to file instead of stdout"
    )
    
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output"
    )
    
    args = parser.parse_args()
    
    # Validate torrent file
    if not os.path.exists(args.torrent_file):
        print(f"Error: Torrent file '{args.torrent_file}' not found")
        return 1
    
    # Setup logging
    if args.quiet:
        log_level = "ERROR"
    else:
        log_level = args.log_level
    
    setup_logging(log_level, args.log_file)
    
    # Create and start client
    client = BitTorrentClient(
        torrent_file=args.torrent_file,
        download_dir=args.download_dir,
        max_peers=args.max_peers,
        port=args.port
    )
    
    print(f"BitTorrent Client - Starting download of {args.torrent_file}")
    print(f"Download directory: {os.path.abspath(args.download_dir)}")
    print(f"Max peers: {args.max_peers}, Port: {args.port}")
    print("Press Ctrl+C to stop\n")
    
    try:
        success = client.start()
        
        if success:
            print("Download completed successfully!")
            return 0
        else:
            print("Download failed or was interrupted")
            return 1
            
    except KeyboardInterrupt:
        print("\nDownload interrupted by user")
        return 130
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
