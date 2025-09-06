#!/usr/bin/env python3
"""
Download and try a known working HTTP tracker torrent
"""

import requests
import os

def download_working_torrent():
    """Download a torrent file that should work with HTTP trackers."""
    
    # Try to download Big Buck Bunny torrent (known to work with HTTP trackers)
    urls = [
        "https://download.blender.org/peach/bigbuckbunny_movies/big_buck_bunny_480p_stereo.ogg.torrent",
        "https://download.blender.org/peach/bigbuckbunny_movies/big_buck_bunny_720p_stereo.ogg.torrent"
    ]
    
    for url in urls:
        try:
            print(f"Downloading torrent from: {url}")
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                filename = url.split('/')[-1]
                with open(filename, 'wb') as f:
                    f.write(response.content)
                print(f"✓ Downloaded: {filename}")
                
                # Test the torrent
                print(f"\nTesting torrent info:")
                os.system(f'C:/Users/5h4h6/Desktop/Network/.venv/Scripts/python.exe main.py --torrent "{filename}" --info')
                return filename
            else:
                print(f"✗ Failed to download: HTTP {response.status_code}")
        except Exception as e:
            print(f"✗ Error downloading {url}: {e}")
    
    return None

if __name__ == "__main__":
    print("Trying to find a working torrent with HTTP trackers...")
    torrent_file = download_working_torrent()
    
    if torrent_file:
        print(f"\n🎉 Try downloading this torrent:")
        print(f'python main.py --torrent "{torrent_file}" --output downloads/')
    else:
        print("\n❌ Could not find a working HTTP tracker torrent.")
        print("Your client works, but most modern torrents use UDP trackers.")
        print("\nFor testing, use the local test setup:")
        print("1. python test_tracker.py    (in terminal 1)")
        print("2. python start_seeder.py    (in terminal 2)")  
        print("3. python main.py --torrent test.torrent --output downloads/  (in terminal 3)")
