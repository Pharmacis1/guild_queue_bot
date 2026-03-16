import sqlite3

db = sqlite3.connect('guild_bot.db')
cur = db.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cur.fetchall()
print("Tables in guild_bot.db:")
for t in tables:
    print(t[0])
db.close()

db2 = sqlite3.connect('guild_bot_2026-03-12_07-49-29_manual_user.db')
cur2 = db2.cursor()
cur2.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables2 = cur2.fetchall()
print("\Tables in manual backup db:")
for t in tables2:
    print(t[0])
db2.close()
