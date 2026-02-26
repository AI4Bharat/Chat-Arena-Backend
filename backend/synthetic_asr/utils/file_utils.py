"""
File utilities for synthetic ASR dataset generation.
Handles JSON, JSONL, and file operations.
Ported from synthetic-benchmarks for Django integration.
"""

import json
import os
import shutil
from typing import List, Dict, Tuple
from pathlib import Path


def save_jsonl_file(data: List[Dict], file_path: str) -> str:
    """
    Save list of dicts as JSONL file (one JSON object per line)
    
    Args:
        data: List of dictionaries
        file_path: Path to save file
        
    Returns:
        Error message if failed, empty string if success
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        return ""
    except Exception as e:
        return f"Error saving JSONL file {file_path}: {str(e)}"


def load_jsonl_file(file_path: str) -> Tuple[List[Dict], str]:
    """
    Load JSONL file (one JSON object per line)
    
    Args:
        file_path: Path to load file
        
    Returns:
        Tuple of (list of dicts, error message)
    """
    data = []
    try:
        if not os.path.exists(file_path):
            return [], f"File not found: {file_path}"
            
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        return [], f"Invalid JSON in file {file_path}: {str(e)}"
        return data, ""
    except Exception as e:
        return [], f"Error loading JSONL file {file_path}: {str(e)}"


def append_to_jsonl_file(data: List[Dict], file_path: str) -> str:
    """
    Append data to existing JSONL file
    
    Args:
        data: List of dictionaries to append
        file_path: Path to file
        
    Returns:
        Error message if failed, empty string if success
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'a', encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        return ""
    except Exception as e:
        return f"Error appending to JSONL file {file_path}: {str(e)}"


def read_json_file(file_path: str) -> Tuple[Dict, str]:
    """
    Read JSON file
    
    Args:
        file_path: Path to JSON file
        
    Returns:
        Tuple of (dict, error message)
    """
    try:
        if not os.path.exists(file_path):
            return {}, f"File not found: {file_path}"
            
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data, ""
    except json.JSONDecodeError as e:
        return {}, f"Invalid JSON in file {file_path}: {str(e)}"
    except Exception as e:
        return {}, f"Error reading JSON file {file_path}: {str(e)}"


def save_json_file(data: Dict, file_path: str) -> str:
    """
    Save dict as JSON file
    
    Args:
        data: Dictionary to save
        file_path: Path to save file
        
    Returns:
        Error message if failed, empty string if success
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return ""
    except Exception as e:
        return f"Error saving JSON file {file_path}: {str(e)}"


def move_file(source: str, dest_dir: str, step: int = 0) -> str:
    """
    Move file to destination directory, optionally renaming with step counter
    
    Args:
        source: Source file path
        dest_dir: Destination directory
        step: Step number for renaming (optional)
        
    Returns:
        Error message if failed, empty string if success
    """
    try:
        os.makedirs(dest_dir, exist_ok=True)
        
        filename = os.path.basename(source)
        if step > 0:
            name, ext = os.path.splitext(filename)
            filename = f"{name}_step{step}{ext}"
        
        dest_path = os.path.join(dest_dir, filename)
        shutil.move(source, dest_path)
        return ""
    except Exception as e:
        return f"Error moving file from {source} to {dest_dir}: {str(e)}"


def copy_file(source: str, dest_dir: str, step: int = 0) -> str:
    """
    Copy file to destination directory, optionally renaming with step counter
    
    Args:
        source: Source file path
        dest_dir: Destination directory
        step: Step number for renaming (optional)
        
    Returns:
        Error message if failed, empty string if success
    """
    try:
        os.makedirs(dest_dir, exist_ok=True)
        
        filename = os.path.basename(source)
        if step > 0:
            name, ext = os.path.splitext(filename)
            filename = f"{name}_step{step}{ext}"
        
        dest_path = os.path.join(dest_dir, filename)
        shutil.copy2(source, dest_path)
        return ""
    except Exception as e:
        return f"Error copying file from {source} to {dest_dir}: {str(e)}"


def file_exists(file_path: str) -> bool:
    """Check if file exists"""
    return os.path.exists(file_path)


def create_directory(dir_path: str) -> str:
    """
    Create directory if it doesn't exist
    
    Args:
        dir_path: Directory path
        
    Returns:
        Error message if failed, empty string if success
    """
    try:
        os.makedirs(dir_path, exist_ok=True)
        return ""
    except Exception as e:
        return f"Error creating directory {dir_path}: {str(e)}"


def remove_file(file_path: str) -> str:
    """
    Remove file if it exists
    
    Args:
        file_path: Path to file
        
    Returns:
        Error message if failed, empty string if success
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        return ""
    except Exception as e:
        return f"Error removing file {file_path}: {str(e)}"


def remove_directory(dir_path: str) -> str:
    """
    Remove directory recursively if it exists
    
    Args:
        dir_path: Directory path
        
    Returns:
        Error message if failed, empty string if success
    """
    try:
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
        return ""
    except Exception as e:
        return f"Error removing directory {dir_path}: {str(e)}"


def get_file_size(file_path: str) -> int:
    """Get file size in bytes"""
    try:
        return os.path.getsize(file_path)
    except Exception:
        return -1


def list_files_in_directory(dir_path: str, pattern: str = "*") -> Tuple[List[str], str]:
    """
    List files in directory matching pattern
    
    Args:
        dir_path: Directory path
        pattern: File pattern (e.g., "*.jsonl")
        
    Returns:
        Tuple of (list of file paths, error message)
    """
    try:
        if not os.path.exists(dir_path):
            return [], f"Directory not found: {dir_path}"
        
        files = [str(p) for p in Path(dir_path).glob(pattern)]
        return files, ""
    except Exception as e:
        return [], f"Error listing files in {dir_path}: {str(e)}"
