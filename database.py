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
conn.commit()



def add_to_conversation(role: str, message: str):
    cursor.execute('''
        INSERT INTO conversation (role, message) VALUES (?, ?)
    ''', (role, message))
    conn.commit()
def read_conversation(limit: int):
    cursor.execute('''
        SELECT role, message FROM conversation ORDER BY timestamp ASC LIMIT ?
    ''', (limit,))
    return [{"role": row[0], "parts": [row[1]]} for row in cursor.fetchall()]

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