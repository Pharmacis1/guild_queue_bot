import sqlite3
import sys

# Set stdout to utf-8 just in case, or just avoid printing unicode
sys.stdout.reconfigure(encoding="utf-8")


def find_user(nickname):
    try:
        conn = sqlite3.connect("guild_bot.db")
        cursor = conn.cursor()
        cursor.execute("SELECT role_id FROM players WHERE nickname = ?", (nickname,))
        results = cursor.fetchall()
        for row in results:
            print(f"Found ID: {row[0]}")
        if not results:
            print(f"No user found with nickname: {nickname}")
        conn.close()
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    find_user("拉格雷克雷")
