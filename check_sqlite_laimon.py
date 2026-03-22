import sqlite3
import os
import sys

DB_NAME = "guild_bot.db"

def check():
    if not os.path.exists(DB_NAME):
        print(f"{DB_NAME} not found.")
        return
        
    conn = sqlite3.connect(DB_NAME)
    sys.stdout.reconfigure(encoding='utf-8')
    
    try:
        cursor = conn.cursor()
        print("--- Searching SQLite 'players' for 'Лаймон' ---")
        cursor.execute("SELECT role_id, nickname, user_id FROM players WHERE nickname LIKE '%Лаймон%'")
        rows = cursor.fetchall()
        for r in rows:
            print(f"RoleID: {r[0]}, Nick: {r[1]!r}, UserID: {r[2]}")
            
        print("\n--- Searching SQLite 'characters' for 'Лаймон' ---")
        cursor.execute("SELECT id, nickname, user_id FROM characters WHERE nickname LIKE '%Лаймон%'")
        rows_c = cursor.fetchall()
        for r in rows_c:
            print(f"ID: {r[0]}, Nick: {r[1]!r}, UserID: {r[2]}")

    finally:
        conn.close()

if __name__ == "__main__":
    check()
