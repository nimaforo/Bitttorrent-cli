# main.py: CLI entry point for BitTorrent client

import os
import sys
import time
import argparse
import logging
from client import Client

def format_size(size):
    """Format size in bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description="Simple BitTorrent CLI Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Download a torrent:
    python main.py --torrent download.torrent --output downloads/

  Show torrent info:
    python main.py --torrent info.torrent --info
        """
    )
    
    parser.add_argument('--torrent', required=True, help="Path to .torrent file")
    parser.add_argument('--output', '-o', help="Output directory for downloads", default='downloads')
    parser.add_argument('--info', '-i', action='store_true', help="Show torrent info only")
    
    args = parser.parse_args()
    
    try:
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        
        # Check if torrent file exists
        if not os.path.exists(args.torrent):
            print(f"\nError: Torrent file '{args.torrent}' not found.")
            print("Please check the file path and try again.")
            sys.exit(1)
        
        # Create output directory
        os.makedirs(args.output, exist_ok=True)
        
        # Load torrent file
        client = Client(args.torrent, args.output)
        torrent = client.torrent
        
        # Show torrent information
        print("\n=== Torrent Information ===")
        print(f"Name: {torrent.name}")
        print(f"Size: {format_size(torrent.total_length)}")
        print(f"Pieces: {torrent.num_pieces} ({format_size(torrent.piece_length)} each)")
        print(f"Tracker: {torrent.announce}")
        
        # Show additional tracker info if available
        if hasattr(torrent, 'announce_list') and torrent.announce_list:
            print(f"Additional trackers: {len(torrent.announce_list)} backup trackers available")
        
        if len(torrent.files) > 1:
            print(f"\nFiles ({len(torrent.files)} total):")
            for file_path, length in torrent.files[:10]:  # Show first 10 files
                print(f"  {file_path} ({format_size(length)})")
            if len(torrent.files) > 10:
                print(f"  ... and {len(torrent.files) - 10} more files")
        
        if args.info:
            print(f"\nTo download this torrent, run:")
            print(f"python main.py --torrent \"{args.torrent}\" --output downloads/")
            return
            
        # Start downloading
        print("\n=== Starting Download ===")
        client.start()
        
    except KeyboardInterrupt:
        print("\nDownload cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()