# torrent.py: Parses .torrent files and extracts metadata

import os
import bencodepy
from utils import sha1_hash

class Torrent:
    def __init__(self, torrent_path):
        """Load and parse a .torrent file."""
        try:
            with open(torrent_path, 'rb') as f:
                meta_info = bencodepy.decode(f.read())
            
            if not isinstance(meta_info, dict):
                raise ValueError("Invalid torrent file format")
            
            # Get the info dictionary
            if b'info' not in meta_info:
                raise ValueError("Missing info dictionary")
            self.info = meta_info[b'info']
            
            # Calculate info hash (used for peer identification)
            self.info_hash = sha1_hash(bencodepy.encode(self.info))
            
            # Get announce URL (tracker)
            if b'announce' not in meta_info:
                raise ValueError("Missing announce URL")
            self.announce = meta_info[b'announce'].decode('utf-8')
            
            # Get announce list if available
            self.announce_list = []
            if b'announce-list' in meta_info:
                for tier in meta_info[b'announce-list']:
                    self.announce_list.append([url.decode('utf-8') for url in tier])
            
            # Get piece length
            if b'piece length' not in self.info:
                raise ValueError("Missing piece length")
            self.piece_length = self.info[b'piece length']
            
            # Get pieces hashes
            if b'pieces' not in self.info:
                raise ValueError("Missing pieces hash")
            pieces = self.info[b'pieces']
            if len(pieces) % 20 != 0:
                raise ValueError("Pieces length not a multiple of 20")
            self.pieces = [pieces[i:i+20] for i in range(0, len(pieces), 20)]
            self.num_pieces = len(self.pieces)
            
            # Handle single file vs multi-file mode
            self.files = []
            self.total_length = 0
            
            # Get name
            if b'name' not in self.info:
                raise ValueError("Missing name in torrent")
            self.name = self.info[b'name'].decode('utf-8')
            
            if b'files' in self.info:  # Multi-file mode
                for file_dict in self.info[b'files']:
                    if b'path' not in file_dict or b'length' not in file_dict:
                        raise ValueError("Invalid file entry in torrent")
                    path_parts = [p.decode('utf-8') for p in file_dict[b'path']]
                    file_path = os.path.join(*path_parts)
                    file_length = file_dict[b'length']
                    self.files.append((file_path, file_length))
                    self.total_length += file_length
            else:  # Single file mode
                if b'length' not in self.info:
                    raise ValueError("Missing length for single file")
                self.files = [(self.name, self.info[b'length'])]
                self.total_length = self.info[b'length']
                
        except Exception as e:
            raise ValueError(f"Error parsing torrent file: {str(e)}")
    
    def get_piece_hash(self, index):
        """Get the expected hash for a piece."""
        if 0 <= index < self.num_pieces:
            return self.pieces[index]
        raise ValueError(f'Invalid piece index {index}')
    
    def piece_size(self, index):
        """Get the size of a piece."""
        if index < self.num_pieces - 1:
            return self.piece_length
        return self.total_length - (self.num_pieces - 1) * self.piece_length
    def verify_piece(self, index, piece_data):
        """Verify that a piece matches its expected hash."""
        if 0 <= index < self.num_pieces:
            piece_hash = sha1_hash(piece_data)
            return piece_hash == self.pieces[index]
        return False
