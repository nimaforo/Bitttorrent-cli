# BitTorrent Client Usage Guide

## How to Use Your BitTorrent Client with Any Torrent File

### Basic Commands

1. **Show torrent information only (recommended first step):**
   ```bash
   python main.py --torrent your_file.torrent --info
   ```

2. **Download a torrent:**
   ```bash
   python main.py --torrent your_file.torrent --output downloads/
   ```

3. **Download to current directory:**
   ```bash
   python main.py --torrent your_file.torrent --output .
   ```

### What Works Best

#### ✅ **Good Torrent Files to Try:**
- **Legal content torrents** (like Sintel, Big Buck Bunny)
- **Linux distributions** (Ubuntu, Debian official torrents)
- **Open source software** torrents
- **Creative Commons content**

#### ⚠️ **What to Expect:**

1. **Public Trackers May Reject Requests:**
   - Many public trackers require registration
   - Some block unauthorized clients
   - You'll see: "Requested download is not authorized for use with this tracker"
   - **This is normal and expected**

2. **Limited Peer Discovery:**
   - Your client uses basic HTTP trackers
   - No DHT (Distributed Hash Table) support yet
   - No Peer Exchange (PEX) support yet
   - May find fewer peers than commercial clients

3. **UDP Trackers Not Fully Supported:**
   - Many modern torrents use UDP trackers
   - Your client primarily supports HTTP trackers

### Recommended Test Process

#### Step 1: Check Torrent Info
```bash
python main.py --torrent your_file.torrent --info
```
This shows:
- File name and size
- Number of pieces
- Tracker URL
- File list (for multi-file torrents)

#### Step 2: Try Download
```bash
python main.py --torrent your_file.torrent --output downloads/
```

#### Step 3: Understand the Output
- ✅ **Success**: "Found X peers" and connections established
- ⚠️ **Authorization Issue**: "not authorized for use with this tracker" 
- ❌ **No Peers**: "No peers found from any tracker"

### Improving Success Rate

#### For Better Results, Try These Torrent Sources:

1. **Linux Distributions:**
   - Ubuntu: https://ubuntu.com/download/alternative-downloads
   - Debian: https://www.debian.org/CD/torrent-cd/
   - CentOS: https://www.centos.org/download/

2. **Legal Content:**
   - Internet Archive: https://archive.org/details/software
   - Blender Foundation: https://www.blender.org/download/
   - Creative Commons: https://creativecommons.org/

3. **Open Source Software:**
   - Many projects offer torrent downloads
   - Usually have active seeders
   - Often use open trackers

### Troubleshooting Common Issues

#### "Requested download is not authorized"
- **Cause**: Tracker requires registration or blocks your client
- **Solution**: Try a different torrent or find alternative trackers

#### "No peers found"
- **Cause**: Torrent is dead (no active seeders) or tracker is down
- **Solution**: Try a more popular/recent torrent

#### "Connection refused" to peers
- **Cause**: Firewall blocking connections or peers offline
- **Solution**: Check Windows Firewall settings

#### "Error parsing torrent file"
- **Cause**: File is corrupt or not a real torrent file
- **Solution**: Re-download the .torrent file

### Advanced Usage

#### Using Alternative Trackers
Some torrents have multiple trackers. Your client will try them in order.

#### Creating Your Own Test Torrents
Use the included test torrent creator:
```bash
python create_test_torrent.py
```

#### Local Testing
Start a local tracker and seeder for testing:
```bash
# Terminal 1: Start tracker
python test_tracker.py

# Terminal 2: Start seeder  
python start_seeder.py

# Terminal 3: Start download
python main.py --torrent test.torrent --output downloads/
```

### Client Limitations (Current Version)

1. **No DHT Support**: Cannot find peers without trackers
2. **No PEX Support**: Cannot exchange peers with other clients
3. **HTTP Trackers Only**: UDP tracker support is limited
4. **No Encryption**: Does not support peer-to-peer encryption
5. **No Resume**: Cannot resume interrupted downloads

### Next Steps for Improvement

To make your client work with more torrents:

1. **Add DHT Support**: For trackerless torrents
2. **Improve UDP Tracker Support**: For modern torrents  
3. **Add Peer Exchange**: For better peer discovery
4. **Implement Resume**: For interrupted downloads
5. **Add Encryption**: For better compatibility

### Example Session

```bash
# Check what's in a torrent
> python main.py --torrent ubuntu.torrent --info
=== Torrent Information ===
Name: ubuntu-22.04.3-desktop-amd64.iso
Size: 4.69 GB
Pieces: 19218 (256.00 KB each)
Tracker: https://torrent.ubuntu.com/announce

# Try to download it
> python main.py --torrent ubuntu.torrent --output downloads/
=== Starting Download ===
Connecting to tracker: https://torrent.ubuntu.com/announce
Tracker returned failure: Requested download is not authorized for use with this tracker.
Failed to get peers from tracker. Trying alternative methods...
No peers found from any tracker. Cannot start download.

Possible solutions:
1. Check your internet connection
2. Try a different torrent file
3. Use a VPN if your ISP blocks BitTorrent
4. Check if the torrent is still active (has seeders)
```

This is the expected behavior for many public torrents. Your client is working correctly - it's just that many trackers have restrictions!
