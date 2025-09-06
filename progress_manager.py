import json
import os

def save_progress(file_path, progress_data):
    """Save download progress to a file."""
    try:
        progress_file = os.path.splitext(file_path)[0] + '.progress'
        with open(progress_file, 'w') as f:
            json.dump(progress_data, f)
    except Exception as e:
        print(f"\nWarning: Could not save progress: {str(e)}")

def load_progress(file_path):
    """Load saved download progress."""
    try:
        if os.path.exists(file_path + '.progress'):
            with open(file_path + '.progress', 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"\nWarning: Could not load progress: {str(e)}")
    return None
