import sqlite3

conn = sqlite3.connect("memory.db")
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
        due_timestamp REAL
    )
''')
conn.commit()

def clear_conversation():
    cursor.execute("DELETE FROM conversation")
    conn.commit()

def add_to_conversation(role: str, message: str):
    cursor.execute('''
        INSERT INTO conversation (role, message) VALUES (?, ?)
    ''', (role, message))
    conn.commit()

def read_conversation(limit: int):
    cursor.execute('''
        SELECT role, message FROM conversation ORDER BY id DESC LIMIT ?
    ''', (limit,))
    rows = cursor.fetchall()
    return [{"role": row[0], "parts": [row[1]]} for row in reversed(rows)]

def add_to_memory(key: str, value: str):
    cursor.execute('''
        INSERT INTO memory (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    ''', (key, value))
    conn.commit()
def read_memory():
    cursor.execute('''
        SELECT key, value FROM memory ''')
    rows = cursor.fetchall()
    if not rows:
        return ''
    return "\n".join(f"{row[0]}: {row[1]}" for row in rows)

def set_setting(key: str, value: str):
    cursor.execute('''
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    ''', (key, value))
    conn.commit()

def get_setting(key: str) -> str | None:
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    return row[0] if row else None

def delete_memory(key: str) -> bool:
    cursor.execute('SELECT key FROM memory WHERE key = ?', (key,))
    if cursor.fetchone():
        cursor.execute('DELETE FROM memory WHERE key = ?', (key,))
        conn.commit()
        return True
    return False

def add_scheduled_task(chat_id: str, task: str, due_timestamp: float):
    cursor.execute('''
        INSERT INTO scheduled_tasks (chat_id, task, due_timestamp) VALUES (?, ?, ?)
    ''', (chat_id, task, due_timestamp))
    conn.commit()

def get_due_tasks(now_timestamp: float):
    cursor.execute('SELECT id, chat_id, task FROM scheduled_tasks WHERE due_timestamp <= ?', (now_timestamp,))
    rows = cursor.fetchall()
    return [{"id": row[0], "chat_id": row[1], "task": row[2]} for row in rows]

def delete_scheduled_task(task_id: int):
    cursor.execute('DELETE FROM scheduled_tasks WHERE id = ?', (task_id,))
    conn.commit()