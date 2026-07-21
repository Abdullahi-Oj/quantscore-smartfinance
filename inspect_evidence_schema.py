import sqlite3
conn = sqlite3.connect('smartfinance.db')
cur = conn.cursor()
cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='evidence'")
print(cur.fetchone()[0])
cur.execute('PRAGMA table_info(evidence)')
for row in cur.fetchall():
    print(row)
conn.close()
