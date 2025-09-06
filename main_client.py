#!/usr/bin/env python3
"""
BitTorrent CLI Client - Main Entry Point

This is the main entry point for the BitTorrent client that coordinates
all components and provides a command-line interface.
"""

import argparse
import signal
import sys
import time
import threading
import logging
import random
import os
from typing import Optional, Set
from pathlib import Path

# Import our modules
from torrent_new import TorrentFile, parse_torrent
from tracker_client import TrackerManager, TrackerEvent
from peer_client import PeerManager, PeerConnection, PeerMessage
from piece_manager_client import PieceManager
from file_manager_client import FileManager
from progress_client import ProgressTracker, ProgressDisplay


class BitTorrentClient:
    """Main BitTorrent client class."""
    
    def __init__(self, torrent_path: str, download_dir: str = "./downloads", 
                 port: int = 6881, max_peers: int = 50, verbose: bool = False):
        """
        Initialize BitTorrent client.
        
        Args:
            torrent_path: Path to .torrent file
            download_dir: Directory to download files to
            port: Port to listen on
            max_peers: Maximum number of peer connections
            verbose: Enable verbose output
        """
        self.torrent_path = torrent_path
        self.download_dir = download_dir
        self.port = port
        self.max_peers = max_peers
        self.verbose = verbose
        
        # Setup logging
        log_level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('bittorrent_client.log'),
                logging.StreamHandler(sys.stdout) if verbose else logging.NullHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Generate peer ID
        self.peer_id = b'-PC0001-' + bytes([random.randint(0, 255) for _ in range(12)])
        
        # Component initialization
        self.torrent = None
        self.tracker_manager = None
        self.peer_manager = None
        self.piece_manager = None
        self.file_manager = None
        self.progress_tracker = None
        self.progress_display = None
        
        # Control flags
        self.running = False
        self.shutdown_event = threading.Event()
        
        # Background threads
        self.announce_thread = None
        self.peer_discovery_thread = None
        self.download_thread = None
        
        # Statistics
        self.start_time = None
        self.completion_time = None
    
    def initialize(self) -> bool:
        """Initialize all client components."""
        try:
            self.logger.info(f"Initializing BitTorrent client for {self.torrent_path}")
            
            # Parse torrent file
            self.torrent = parse_torrent(self.torrent_path)
            self.logger.info(f"Loaded torrent: {self.torrent.name}")
            self.logger.info(f"Size: {self.torrent.total_size:,} bytes ({self.torrent.num_pieces} pieces)")
            
            # Initialize file manager
            self.file_manager = FileManager(self.torrent, self.download_dir)
            
            # Check storage space
            storage_info = self.file_manager.get_storage_info()
            if not storage_info.get('sufficient_space', False):
                self.logger.error("Insufficient storage space!")
                return False
            
            # Initialize piece manager
            self.piece_manager = PieceManager(self.torrent, self._on_piece_completed)
            
            # Check for existing pieces (resume functionality)
            existing_pieces = self.file_manager.check_existing_pieces()
            for piece_index in existing_pieces:
                self.piece_manager.mark_piece_complete(piece_index)
            
            if existing_pieces:
                self.logger.info(f"Resuming download: {len(existing_pieces)} pieces already completed")
            
            # Initialize tracker manager
            self.tracker_manager = TrackerManager(
                self.torrent.announce_list, 
                self.torrent.info_hash, 
                self.peer_id
            )
            
            # Initialize peer manager
            self.peer_manager = PeerManager(
                self.torrent.info_hash,
                self.peer_id,
                self.torrent.num_pieces,
                self.max_peers
            )
            
            # Initialize progress tracking
            self.progress_tracker = ProgressTracker(
                self.torrent.total_size,
                self.torrent.num_pieces
            )
            
            self.progress_display = ProgressDisplay(
                self.torrent.name,
                self.progress_tracker,
                verbose=self.verbose
            )
            
            # Allocate files
            if not self.file_manager.allocate_files(sparse=True):
                self.logger.error("Failed to allocate files")
                return False
            
            self.logger.info("Client initialization completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize client: {e}")
            return False
    
    def _on_piece_completed(self, piece_index: int, piece_data: bytes):
        """Handle completed piece."""
        # Write piece to disk
        if self.file_manager.write_piece(piece_index, piece_data):
            self.logger.debug(f"Piece {piece_index} written to disk")
            
            # Notify all peers that we have this piece
            for peer in self.peer_manager.get_active_peers():
                peer.send_have(piece_index)
        
        else:
            self.logger.error(f"Failed to write piece {piece_index} to disk")
    
    def _peer_message_handler(self, peer: PeerConnection, message_id: int, payload):
        """Handle messages from peers."""
        if message_id == PeerMessage.PIECE.value and isinstance(payload, tuple):
            piece_index, block_offset, block_data = payload
            
            # Add block to piece manager
            self.piece_manager.add_block(piece_index, block_offset, block_data)
        
        elif message_id == PeerMessage.HAVE.value:
            # Peer has a new piece - handled by peer connection itself
            pass
        
        elif message_id == PeerMessage.BITFIELD.value:
            # Peer sent bitfield - handled by peer connection itself
            pass
    
    def _announce_loop(self):
        """Background thread for periodic tracker announces."""
        announce_interval = 1800  # 30 minutes default
        last_announce = 0
        
        while self.running and not self.shutdown_event.wait(10):
            try:
                current_time = time.time()
                
                if current_time - last_announce >= announce_interval:
                    # Announce to trackers
                    uploaded = sum(peer.bytes_uploaded for peer in self.peer_manager.get_active_peers())
                    downloaded = self.piece_manager.get_downloaded_bytes()
                    left = self.piece_manager.get_remaining_bytes()
                    
                    event = TrackerEvent.NONE
                    if last_announce == 0:
                        event = TrackerEvent.STARTED
                    elif left == 0:
                        event = TrackerEvent.COMPLETED
                    
                    responses = self.tracker_manager.announce_to_all(
                        self.port, uploaded, downloaded, left, event
                    )
                    
                    if responses:
                        announce_interval = min(resp.interval for resp in responses)
                        self.logger.debug(f"Next announce in {announce_interval} seconds")
                    
                    last_announce = current_time
                
            except Exception as e:
                self.logger.error(f"Error in announce loop: {e}")
    
    def _peer_discovery_loop(self):
        """Background thread for discovering and connecting to new peers."""
        while self.running and not self.shutdown_event.wait(30):
            try:
                # Get current number of active peers
                active_peers = len(self.peer_manager.get_active_peers())
                
                if active_peers < self.max_peers:
                    # Get more peers from trackers
                    uploaded = sum(peer.bytes_uploaded for peer in self.peer_manager.get_active_peers())
                    downloaded = self.piece_manager.get_downloaded_bytes()
                    left = self.piece_manager.get_remaining_bytes()
                    
                    new_peers = self.tracker_manager.get_peers(
                        self.port, uploaded, downloaded, left
                    )
                    
                    # Try to connect to new peers
                    for peer_ip, peer_port in new_peers[:10]:  # Limit to 10 new peers at once
                        if len(self.peer_manager.get_active_peers()) >= self.max_peers:
                            break
                        
                        self.peer_manager.add_peer(peer_ip, peer_port, self._peer_message_handler)
                
                # Cleanup dead peers
                self.peer_manager.cleanup_dead_peers()
                
            except Exception as e:
                self.logger.error(f"Error in peer discovery loop: {e}")
    
    def _download_loop(self):
        """Main download coordination loop."""
        while self.running and not self.shutdown_event.wait(1):
            try:
                # Update progress
                active_peers = self.peer_manager.get_active_peers()
                downloaded = self.piece_manager.get_downloaded_bytes()
                uploaded = sum(peer.bytes_uploaded for peer in active_peers)
                completed_pieces = len(self.piece_manager.completed_pieces)
                
                self.progress_tracker.update_progress(
                    downloaded, uploaded, completed_pieces, len(active_peers)
                )
                
                # Check if download is complete
                if self.piece_manager.is_complete():
                    self.logger.info("Download completed!")
                    self.completion_time = time.time()
                    break
                
                # Request blocks from peers
                for peer in active_peers:
                    if peer.can_request():
                        # Get blocks to request
                        requests = self.piece_manager.get_next_pieces_for_peer(
                            peer.state.pieces_available, 5
                        )
                        
                        for piece_index, block_offset, block_length in requests:
                            peer.send_request(piece_index, block_offset, block_length)
                
                # Send interested message to new peers
                for peer in active_peers:
                    if not peer.state.am_interested and peer.state.pieces_available:
                        peer.send_interested()
                
                # Cleanup expired requests
                self.piece_manager.cleanup_expired_requests()
                
            except Exception as e:
                self.logger.error(f"Error in download loop: {e}")
    
    def start(self):
        """Start the BitTorrent client."""
        if self.running:
            return
        
        self.logger.info("Starting BitTorrent client...")
        self.running = True
        self.start_time = time.time()
        
        # Start progress display
        self.progress_display.start()
        
        # Start background threads
        self.announce_thread = threading.Thread(target=self._announce_loop, daemon=True)
        self.announce_thread.start()
        
        self.peer_discovery_thread = threading.Thread(target=self._peer_discovery_loop, daemon=True)
        self.peer_discovery_thread.start()
        
        self.download_thread = threading.Thread(target=self._download_loop, daemon=True)
        self.download_thread.start()
        
        self.logger.info("BitTorrent client started successfully")
    
    def stop(self):
        """Stop the BitTorrent client."""
        if not self.running:
            return
        
        self.logger.info("Stopping BitTorrent client...")
        self.running = False
        self.shutdown_event.set()
        
        # Stop progress display
        if self.progress_display:
            self.progress_display.stop()
        
        # Announce stopped to trackers
        if self.tracker_manager and self.piece_manager:
            try:
                uploaded = sum(peer.bytes_uploaded for peer in self.peer_manager.get_active_peers())
                downloaded = self.piece_manager.get_downloaded_bytes()
                left = self.piece_manager.get_remaining_bytes()
                
                self.tracker_manager.announce_to_all(
                    self.port, uploaded, downloaded, left, TrackerEvent.STOPPED
                )
            except Exception as e:
                self.logger.error(f"Error announcing stop: {e}")
        
        # Disconnect all peers
        if self.peer_manager:
            self.peer_manager.disconnect_all()
        
        # Close file handles
        if self.file_manager:
            self.file_manager.close_all_files()
        
        # Wait for threads to finish
        for thread in [self.announce_thread, self.peer_discovery_thread, self.download_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=5)
        
        self.logger.info("BitTorrent client stopped")
    
    def run(self):
        """Run the client until completion or interruption."""
        try:
            self.start()
            
            # Wait for completion or interruption
            while self.running:
                if self.piece_manager.is_complete():
                    self.progress_display.print_final_summary()
                    break
                
                time.sleep(1)
        
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
        
        finally:
            self.stop()


def signal_handler(signum, frame):
    """Handle interrupt signals."""
    print("\nReceived interrupt signal. Shutting down gracefully...")
    # The main loop will catch this and shut down properly


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="BitTorrent CLI Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py example.torrent
  python main.py example.torrent -d /home/user/downloads
  python main.py example.torrent -p 6882 -m 100 -v
        """
    )
    
    parser.add_argument(
        "torrent_file",
        help="Path to .torrent file"
    )
    
    parser.add_argument(
        "-d", "--download-dir",
        default="./downloads",
        help="Directory to download files to (default: ./downloads)"
    )
    
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=6881,
        help="Port to listen on (default: 6881)"
    )
    
    parser.add_argument(
        "-m", "--max-peers",
        type=int,
        default=50,
        help="Maximum number of peer connections (default: 50)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    # Validate torrent file
    if not os.path.exists(args.torrent_file):
        print(f"Error: Torrent file '{args.torrent_file}' not found")
        sys.exit(1)
    
    # Create download directory
    Path(args.download_dir).mkdir(parents=True, exist_ok=True)
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and run client
    client = BitTorrentClient(
        torrent_path=args.torrent_file,
        download_dir=args.download_dir,
        port=args.port,
        max_peers=args.max_peers,
        verbose=args.verbose
    )
    
    if not client.initialize():
        print("Failed to initialize BitTorrent client")
        sys.exit(1)
    
    print(f"BitTorrent CLI Client")
    print(f"====================")
    print(f"Torrent file: {args.torrent_file}")
    print(f"Download directory: {args.download_dir}")
    print(f"Port: {args.port}")
    print(f"Max peers: {args.max_peers}")
    print()
    
    try:
        client.run()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
