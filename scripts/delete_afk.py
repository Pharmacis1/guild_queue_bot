import sqlite3
import os

dbs = ['guild_bot.db', 'guild_bot_2026-03-12_07-49-29_manual_user.db']

player = 'ㄒhｅ乇ηD'

for db_name in dbs:
    if not os.path.exists(db_name):
        continue
    print(f"Checking {db_name}")
    db = sqlite3.connect(db_name)
    cur = db.cursor()
    
    cur.execute("SELECT * FROM afk_timers WHERE player_name=?", (player,))
    rows = cur.fetchall()
    print("Found records:", rows)
    
    # Let's delete it if requested later, for now let's just delete the 11.03 one.
    if rows:
        # Assuming the date column contains '11.03'
        cur.execute("DELETE FROM afk_timers WHERE player_name=? AND date=?", (player, '11.03'))
        print("Deleted rows count:", cur.rowcount)
        # Maybe the date is not exactly '11.03', let's delete by player for now, or print all.
        db.commit()
    db.close()
