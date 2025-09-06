#!/usr/bin/env python3
"""
Enhanced BitTorrent client with full protocol support.
Supports HTTP/HTTPS trackers, UDP trackers, DHT, PEX, WebSeeds, and more.
"""

import sys
import os
import argparse
import time
from pathlib import Path

def analyze_torrent(torrent_path):
    """Analyze torrent file and show detailed information."""
    try:
        from torrent import Torrent
        
        print("=" * 60)
        print("🔍 ENHANCED TORRENT ANALYSIS")
        print("=" * 60)
        
        torrent = Torrent(torrent_path)
        
        # Basic info
        print(f"📁 Name: {torrent.name}")
        print(f"📊 Size: {torrent.total_length / (1024**3):.2f} GB ({torrent.total_length:,} bytes)")
        print(f"🧩 Pieces: {torrent.num_pieces:,} pieces ({torrent.piece_length / (1024**2):.2f} MB each)")
        print(f"🔑 Info Hash: {torrent.info_hash.hex() if isinstance(torrent.info_hash, bytes) else torrent.info_hash}")
        
        # Files
        if hasattr(torrent, 'files') and torrent.files:
            print(f"\n📂 Files ({len(torrent.files)}):")
            for i, file_info in enumerate(torrent.files[:10]):  # Show first 10 files
                if isinstance(file_info, dict):
                    file_path = '/'.join(file_info['path'])
                    file_size = file_info['length'] / (1024**2)
                else:
                    # Handle tuple format
                    file_path = str(file_info)
                    file_size = 0
                print(f"   {i+1:2d}. {file_path} ({file_size:.1f} MB)")
            if len(torrent.files) > 10:
                print(f"   ... and {len(torrent.files) - 10} more files")
        else:
            print(f"\n📂 Single file: {torrent.name}")
        
        # Trackers
        print(f"\n📡 Primary Tracker: {torrent.announce}")
        
        tracker_types = set()
        total_trackers = 1
        
        if hasattr(torrent, 'announce_list') and torrent.announce_list:
            total_trackers = sum(len(tier) for tier in torrent.announce_list)
            print(f"📋 Backup Trackers: {total_trackers - 1} additional trackers")
            
            print("\n🌐 Tracker Types Found:")
            for tier in torrent.announce_list:
                for tracker in tier:
                    if tracker.startswith('http://'):
                        tracker_types.add('HTTP')
                    elif tracker.startswith('https://'):
                        tracker_types.add('HTTPS') 
                    elif tracker.startswith('udp://'):
                        tracker_types.add('UDP')
                    elif tracker.startswith('ws://') or tracker.startswith('wss://'):
                        tracker_types.add('WebSocket')
            
            for tracker_type in sorted(tracker_types):
                if tracker_type == 'UDP':
                    print(f"   ✅ {tracker_type} - Full support")
                elif tracker_type in ['HTTP', 'HTTPS']:
                    print(f"   ✅ {tracker_type} - Full support")
                elif tracker_type == 'WebSocket':
                    print(f"   ⚠️  {tracker_type} - Limited support")
                else:
                    print(f"   ❓ {tracker_type} - Unknown")
        
        # WebSeeds
        if hasattr(torrent, 'url_list') and torrent.url_list:
            print(f"\n🌍 WebSeeds: {len(torrent.url_list)} HTTP/FTP sources")
            for url in torrent.url_list[:3]:
                print(f"   • {url}")
            if len(torrent.url_list) > 3:
                print(f"   ... and {len(torrent.url_list) - 3} more")
        
        # DHT support
        print(f"\n🕸️  DHT Support: {'✅ Enabled' if getattr(torrent, 'dht', True) else '❌ Disabled'}")
        
        # Compatibility assessment
        print(f"\n🎯 COMPATIBILITY ASSESSMENT")
        print("=" * 40)
        
        compatibility_score = 0
        max_score = 5
        
        if 'HTTP' in tracker_types or 'HTTPS' in tracker_types:
            print("✅ HTTP/HTTPS trackers: Excellent support")
            compatibility_score += 2
        
        if 'UDP' in tracker_types:
            print("✅ UDP trackers: Full support")
            compatibility_score += 2
        
        if hasattr(torrent, 'url_list') and torrent.url_list:
            print("✅ WebSeeds: Direct download fallback available")
            compatibility_score += 1
        
        if total_trackers > 5:
            print("✅ Multiple trackers: Good redundancy")
        elif total_trackers > 1:
            print("⚠️  Few trackers: Limited redundancy")
        else:
            print("❌ Single tracker: No redundancy")
        
        print(f"\n🔥 Overall Compatibility: {compatibility_score}/{max_score}")
        if compatibility_score >= 4:
            print("🎉 Excellent - Should download successfully")
        elif compatibility_score >= 2:
            print("👍 Good - Should work with some effort")
        else:
            print("⚠️  Poor - May have difficulty downloading")
        
        return True
        
    except Exception as e:
        print(f"❌ Error analyzing torrent: {e}")
        return False

def download_with_enhanced_client(torrent_path, output_dir):
    """Download using the enhanced client."""
    try:
        from enhanced_client import EnhancedBitTorrentClient
        
        print("🚀 Starting Enhanced BitTorrent Client")
        print("=" * 50)
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Create and start client
        client = EnhancedBitTorrentClient(torrent_path, output_dir)
        success = client.start_download()
        
        if success:
            print("\n🎉 Download completed successfully!")
            return True
        else:
            print("\n❌ Download failed")
            return False
            
    except ImportError:
        print("⚠️  Enhanced client not available, falling back to standard client...")
        return download_with_standard_client(torrent_path, output_dir)
    except Exception as e:
        print(f"❌ Enhanced client error: {e}")
        print("⚠️  Falling back to standard client...")
        return download_with_standard_client(torrent_path, output_dir)

def download_with_standard_client(torrent_path, output_dir):
    """Download using the standard client."""
    try:
        from client import Client
        
        print("🔧 Using Standard BitTorrent Client")
        print("=" * 50)
        
        os.makedirs(output_dir, exist_ok=True)
        
        client = Client(torrent_path, output_dir, seed=False)
        client.start()
        return True
        
    except Exception as e:
        print(f"❌ Standard client error: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description='Enhanced BitTorrent Client with full protocol support',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --torrent movie.torrent --output downloads/
  python main.py --analyze movie.torrent
  python main.py --torrent movie.torrent --output downloads/ --enhanced
        """
    )
    
    parser.add_argument('--torrent', '-t', required=True,
                       help='Path to .torrent file')
    parser.add_argument('--output', '-o', default='./downloads',
                       help='Output directory for downloads (default: ./downloads)')
    parser.add_argument('--analyze', '-a', action='store_true',
                       help='Only analyze torrent file, don\'t download')
    parser.add_argument('--enhanced', '-e', action='store_true',
                       help='Force use of enhanced client')
    parser.add_argument('--standard', '-s', action='store_true',
                       help='Force use of standard client')
    
    args = parser.parse_args()
    
    # Check if torrent file exists
    if not os.path.exists(args.torrent):
        print(f"❌ Torrent file not found: {args.torrent}")
        return 1
    
    # Analyze torrent
    print("🔍 Analyzing torrent file...")
    if not analyze_torrent(args.torrent):
        return 1
    
    # If only analyzing, exit here
    if args.analyze:
        return 0
    
    print("\n" + "=" * 60)
    print("🚀 STARTING DOWNLOAD")
    print("=" * 60)
    
    # Choose client
    if args.standard:
        success = download_with_standard_client(args.torrent, args.output)
    elif args.enhanced:
        success = download_with_enhanced_client(args.torrent, args.output)
    else:
        # Auto-select best client
        success = download_with_enhanced_client(args.torrent, args.output)
    
    return 0 if success else 1

if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⏹️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
