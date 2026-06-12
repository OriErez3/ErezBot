import sqlite3
import threading
from pathlib import Path

#Anchor the DB next to this file so the bot finds it no matter where it's launched from
DB_PATH = Path(__file__).resolve().parent / "memory.db"
#check_same_thread=False because tools run in worker threads; the lock serializes all
#access since a sqlite connection can't be used by two threads at once
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_lock = threading.Lock()
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS conversation (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT,
        message TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE,
        value TEXT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS scheduled_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        task TEXT,
        due_timestamp REAL,
        status TEXT DEFAULT 'pending'
    )
''')
#Migration for databases created before the status column existed
try:
    cursor.execute("ALTER TABLE scheduled_tasks ADD COLUMN status TEXT DEFAULT 'pending'")
except sqlite3.OperationalError:
    pass  #column already exists
conn.commit()

def clear_conversation():
    with _lock:
        cursor.execute("DELETE FROM conversation")
        conn.commit()

def add_to_conversation(role: str, message: str):
    with _lock:
        cursor.execute('''
            INSERT INTO conversation (role, message) VALUES (?, ?)
        ''', (role, message))
        conn.commit()

def read_conversation(limit: int):
    with _lock:
        cursor.execute('''
            SELECT role, message FROM conversation ORDER BY id DESC LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
    return [{"role": row[0], "parts": [row[1]]} for row in reversed(rows)]

def add_to_memory(key: str, value: str):
    with _lock:
        cursor.execute('''
            INSERT INTO memory (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        ''', (key, value))
        conn.commit()
def read_memory():
    with _lock:
        cursor.execute('''
            SELECT key, value FROM memory ''')
        rows = cursor.fetchall()
    if not rows:
        return ''
    return "\n".join(f"{row[0]}: {row[1]}" for row in rows)

def set_setting(key: str, value: str):
    with _lock:
        cursor.execute('''
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        ''', (key, value))
        conn.commit()

def get_setting(key: str) -> str | None:
    with _lock:
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = cursor.fetchone()
    return row[0] if row else None

def delete_memory(key: str) -> bool:
    with _lock:
        cursor.execute('SELECT key FROM memory WHERE key = ?', (key,))
        if cursor.fetchone():
            cursor.execute('DELETE FROM memory WHERE key = ?', (key,))
            conn.commit()
            return True
    return False

def add_scheduled_task(chat_id: str, task: str, due_timestamp: float):
    with _lock:
        cursor.execute('''
            INSERT INTO scheduled_tasks (chat_id, task, due_timestamp, status) VALUES (?, ?, ?, 'pending')
        ''', (chat_id, task, due_timestamp))
        conn.commit()

def get_due_tasks(now_timestamp: float):
    with _lock:
        cursor.execute("SELECT id, chat_id, task FROM scheduled_tasks WHERE due_timestamp <= ? AND status = 'pending'", (now_timestamp,))
        rows = cursor.fetchall()
    return [{"id": row[0], "chat_id": row[1], "task": row[2]} for row in rows]

def mark_task_running(task_id: int):
    with _lock:
        cursor.execute("UPDATE scheduled_tasks SET status = 'running' WHERE id = ?", (task_id,))
        conn.commit()

def reset_running_tasks() -> int:
    """Re-queues tasks left in 'running' by a crash so they aren't silently lost.
    Returns how many were re-queued (a re-queued task may run twice if the crash
    happened after the action but before cleanup)."""
    with _lock:
        cursor.execute("UPDATE scheduled_tasks SET status = 'pending' WHERE status = 'running'")
        conn.commit()
        return cursor.rowcount

def delete_scheduled_task(task_id: int):
    with _lock:
        cursor.execute('DELETE FROM scheduled_tasks WHERE id = ?', (task_id,))
        conn.commit()
