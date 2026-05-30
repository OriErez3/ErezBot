import subprocess
from database import add_to_memory
import sqlite3
import os 
conn = sqlite3.connect("memory.db")
cursor = conn.cursor()

def run_shell(command: str) -> str:
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            capture_output=True, 
            text=True,
            encoding="utf-8",
            errors="replace"  # replaces undecodable characters instead of crashing
        )
        return result.stdout + result.stderr
    except Exception as e:
        return f"Error: {e}"

def save_memory(key: str, value: str):
    add_to_memory(key, value)
    return f"Memory saved: {key} = {value}"

def delete_memory(key: str):
    cursor.execute('''SELECT key FROM memory WHERE key = ?''', (key,))
    if cursor.fetchone():
        cursor.execute('''DELETE FROM memory WHERE key = ?''', (key,))
        conn.commit()
        return f"Memory deleted: {key}"
    return f"Memory not found: {key}"

def list_directory(path: str = ".") -> str:
    try:
        # normalize the path so forward and back slashes both work
        path = os.path.normpath(path)
        print(f"Listing: {path}")
        print(f"Exists: {os.path.exists(path)}")
        if not os.path.exists(path):
            return f"Path does not exist: {path}"
        if not os.path.isdir(path):
            return f"{path} is a file, not a directory"
        files = os.listdir(path)
        if not files:
            return f"Directory is empty: {path}"
        return "\n".join(files)
    except Exception as e:
        return f"Error: {e}"

def read_file(file_path: str) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
            return content
    except Exception as e:
        return f"Error: {e}"

def write_file(path: str, content: str) -> str:
    try:
        with open(path, "w", encoding="utf-8") as file:
            file.write(content)
        return "Successfully written!"
    except Exception as e:
        return f"Error: {e}"
    
def find_file(filename: str) -> str:
    import os
    search_paths = [
        os.path.expanduser("~"),  # home directory
        os.path.expanduser("~/Desktop"),
        os.path.expanduser("~/Documents"),
        os.path.expanduser("~/Downloads"),
    ]
    
    matches = []
    for path in search_paths:
        if os.path.exists(path):
            for root, dirs, files in os.walk(path):
                for file in files:
                    if filename.lower() in file.lower():
                        matches.append(os.path.join(root, file))
    
    return "\n".join(matches) if matches else "No files found"