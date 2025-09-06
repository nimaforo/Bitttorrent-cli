# file_manager.py: Handles file creation and writing for multi-file torrents.
import os
import logging
from utils import sha1_hash

class FileManager:
    def __init__(self, torrent, output_path):
        self.torrent = torrent
        self.output_path = os.path.abspath(os.path.normpath(output_path))
        self.files = []
        self.downloaded = 0
        self._init_files()

    def _init_files(self):
        """Initialize file list and create directories."""
        info = self.torrent.info
        name = info.get('name') or info.get(b'name') or 'downloaded_torrent'
        if isinstance(name, bytes):
            name = name.decode(errors='ignore')
        if 'files' in info:
            # Multi-file mode
            base_path = os.path.join(self.output_path, name)
            for f in info['files']:
                length = f.get('length') or f.get(b'length')
                path_parts = f.get('path') or f.get(b'path')
                if isinstance(path_parts, list):
                    path = os.path.join(base_path, *(p.decode() if isinstance(p, bytes) else p for p in path_parts))
                else:
                    path = os.path.join(base_path, path_parts.decode() if isinstance(path_parts, bytes) else path_parts)
                self.files.append({'path': path, 'length': length, 'offset': 0})
                os.makedirs(os.path.dirname(path), exist_ok=True)
        else:
            # Single file mode
            length = info.get('length') or info.get(b'length')
            path = os.path.join(self.output_path, name)
            self.files.append({'path': path, 'length': length, 'offset': 0})
            os.makedirs(os.path.dirname(path), exist_ok=True)

    def write_block(self, index, begin, block):
        """Write a block of data to disk."""
        offset = index * self.torrent.piece_length + begin
        remaining = len(block)
        block_offset = 0
        for f in self.files:
            if offset >= f['offset'] + f['length']:
                continue
            if offset < f['offset']:
                continue
            file_offset = offset - f['offset']
            to_write = min(remaining, f['length'] - file_offset)
            try:
                with open(f['path'], 'r+b') as fh:
                    fh.seek(file_offset)
                    fh.write(block[block_offset:block_offset+to_write])
            except IOError as e:
                logging.error(f"Failed to write block to {f['path']}: {e}")
                return False
            offset += to_write
            block_offset += to_write
            remaining -= to_write
            if remaining == 0:
                break
        self.downloaded += len(block)
        return True

    def read_block(self, index, begin, length):
        """Read a block of data from disk."""
        offset = index * self.torrent.piece_length + begin
        block = b''
        remaining = length
        for f in self.files:
            if offset >= f['offset'] + f['length']:
                continue
            if offset < f['offset']:
                continue
            file_offset = offset - f['offset']
            to_read = min(remaining, f['length'] - file_offset)
            try:
                with open(f['path'], 'rb') as fh:
                    fh.seek(file_offset)
                    block += fh.read(to_read)
            except IOError as e:
                logging.error(f"Failed to read block from {f['path']}: {e}")
                return None
            offset += to_read
            remaining -= to_read
            if remaining == 0:
                break
        return block if len(block) == length else None

    def validate_piece(self, index, piece_data):
        """Validate a piece against its hash."""
        if index >= len(self.torrent.piece_hashes):
            logging.error(f"Invalid piece index {index}")
            return False
        computed_hash = sha1_hash(piece_data)
        expected_hash = self.torrent.piece_hashes[index]
        if computed_hash != expected_hash:
            logging.error(f"Hash mismatch for piece {index}")
            logging.error(f"Expected: {expected_hash.hex()}")
            logging.error(f"Got: {computed_hash.hex()}")
            return False
        return True

    def get_downloaded(self):
        return self.downloaded

    def close(self):
        pass  # No persistent file handles to close in this implementation

    def read_piece(self, index):
        piece_length = self.torrent.piece_length
        if index == self.torrent.num_pieces - 1:
            piece_length = self.torrent.total_length - (index * self.torrent.piece_length)
        return self.read_block(index, 0, piece_length)
