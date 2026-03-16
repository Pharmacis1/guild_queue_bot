import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

for db_name in ['guild_bot.db', 'guild_bot_2026-03-12_07-49-29_manual_user.db']:
    print(f"\n--- Checking {db_name} ---")
    try:
        db = sqlite3.connect(db_name)
        cur = db.cursor()
        cur.execute("SELECT id, telegram_id, username, afk_start, afk_end, afk_reason FROM users WHERE afk_start IS NOT NULL")
        users = cur.fetchall()
        for u in users:
            print("AFK User:", u)
        
        cur.execute("SELECT role_id, user_id, nickname FROM players WHERE nickname LIKE '%D%'")
        players = cur.fetchall()
        for p in players:
            print("Player LIKE '%D%':", p)
        db.close()
    except Exception as e:
        print("Error:", e)
