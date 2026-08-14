import sqlite3
import json

conn = sqlite3.connect('issues.db')
cursor = conn.cursor()
cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
for name, sql in tables:
    print(f"Table: {name}")
    print(sql)
    print("-" * 50)
    
cursor.execute("SELECT * FROM parsed_changelogs LIMIT 2")
print("parsed_changelogs sample:")
print(cursor.fetchall())
conn.close()
