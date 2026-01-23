"""
Migration script to add avatar_url column to users table
"""
import sqlite3

DB_PATH = "guild_bot.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'avatar_url' not in columns:
        print("Adding avatar_url column to users table...")
        cursor.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
        conn.commit()
        print("[OK] Migration completed successfully!")
    else:
        print("[INFO] Column avatar_url already exists, skipping migration.")
    
    conn.close()

if __name__ == "__main__":
    migrate()
