import subprocess
from database import add_to_memory
import sqlite3
conn = sqlite3.connect("memory.db")
cursor = conn.cursor()

def run_shell(command: str) -> str:
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.stdout + result.stderr

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
