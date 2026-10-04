import sqlite3
from pathlib import Path

# Path to the curriculum SQLite DB (relative to repository root)
DB_PATH = Path('work') / 'lab8b_run' / 'curriculum.db'

query = """
SELECT p.code, c.name_th
FROM prerequisite p
JOIN course c ON p.code = c.code
WHERE p.requires = '06016317'
LIMIT 200;
"""

conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()
cur.execute(query)
rows = cur.fetchall()
print('Rows returned:', len(rows))
for row in rows:
    print(row)
conn.close()
