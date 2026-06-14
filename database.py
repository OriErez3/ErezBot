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
cursor.execute('''
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT
    )
''')
#Migration for databases created before conversations existed: add conversation_id to
#existing messages (DEFAULT 1 backfills old rows) and register conversation 1 for them
try:
    cursor.execute("ALTER TABLE conversation ADD COLUMN conversation_id INTEGER DEFAULT 1")
except sqlite3.OperationalError:
    pass  #column already exists
cursor.execute("INSERT OR IGNORE INTO conversations (id, title) VALUES (1, 'Conversation 1')")
conn.commit()

def clear_conversation(conversation_id: int):
    with _lock:
        cursor.execute("DELETE FROM conversation WHERE conversation_id = ?", (conversation_id,))
        conn.commit()

def add_to_conversation(role: str, message: str, conversation_id: int):
    with _lock:
        cursor.execute('''
            INSERT INTO conversation (role, message, conversation_id) VALUES (?, ?, ?)
        ''', (role, message, conversation_id))
        conn.commit()

def read_conversation(limit: int, conversation_id: int):
    with _lock:
        cursor.execute('''
            SELECT role, message FROM conversation WHERE conversation_id = ? ORDER BY id DESC LIMIT ?
        ''', (conversation_id, limit))
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

def get_active_conversation_id() -> int:
    value = get_setting("active_conversation_id")
    return int(value) if value else 1

def set_active_conversation_id(conversation_id: int) -> None:
    set_setting("active_conversation_id", str(conversation_id))

def create_conversation() -> int:
    with _lock:
        cursor.execute("INSERT INTO conversations (title) VALUES (NULL)")
        new_id = cursor.lastrowid
        cursor.execute("UPDATE conversations SET title = ? WHERE id = ?", (f"Conversation {new_id}", new_id))
        conn.commit()
    return new_id #type: ignore

def list_conversations():
    with _lock:
        cursor.execute("SELECT id, title FROM conversations ORDER BY id")
        rows = cursor.fetchall()
    return [{"id": row[0], "title": row[1]} for row in rows]

def conversation_exists(conversation_id: int) -> bool:
    with _lock:
        cursor.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,))
        return cursor.fetchone() is not None

def rename_conversation(conversation_id: int, title: str) -> None:
    with _lock:
        cursor.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id))
        conn.commit()
