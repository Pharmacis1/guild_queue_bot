import sqlite3
import os

DB_NAME = "guild_bot_2026-03-20_06-29-42_manual_user.db"

def check():
    if not os.path.exists(DB_NAME):
        return
    conn = sqlite3.connect(DB_NAME)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT in_clan FROM players WHERE role_id = 61136")
        row = cursor.fetchone()
        if row:
            print(f"Role 61136 InClan in backup: {row[0]}")
    finally:
        conn.close()

if __name__ == "__main__":
    check()
