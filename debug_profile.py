import sqlite3
import json

db_name = "guild_bot.db"
conn = sqlite3.connect(db_name)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

role_id = 38816 # BladeRNNR in screenshot

# 1. Basic info
cursor.execute("SELECT user_id, nickname FROM players WHERE role_id = ?", (role_id,))
r = cursor.fetchone()
if not r:
    print("Player not found")
    exit()

user_id = r['user_id']
print(f"User ID: {user_id}")

# 2. Linked chars
c_sql = """
    SELECT c.nickname, c.is_main, p.class_id 
    FROM characters c
    LEFT JOIN players p ON LOWER(c.nickname) = LOWER(p.nickname)
    WHERE c.user_id = ?
"""
cursor.execute(c_sql, (user_id,))
c_rows = cursor.fetchall()
linked_chars = [dict(cr) for cr in c_rows]

print("\nLinked Characters Result:")
print(json.dumps(linked_chars, indent=2))

conn.close()
