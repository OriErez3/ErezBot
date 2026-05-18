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
        message TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
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

def add_to_memory(role: str, message: str):
    cursor.execute('''
        INSERT INTO memory (message) VALUES (?)
    ''', (message,))
    conn.commit()
def read_memory(limit: int):
    cursor.execute('''
        SELECT message FROM memory ORDER BY timestamp DESC LIMIT ?
    ''', (limit,))
    return cursor.fetchall()