import sqlite3

DB_NAME = "guild_bot.db"


def migrate():
    print(f"Checking for afk_history table in {DB_NAME}...")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='afk_history'")
        if cursor.fetchone():
            print("Table 'afk_history' already exists.")
        else:
            print("Table 'afk_history' NOT found. Creating...")
            cursor.execute("""
                CREATE TABLE afk_history (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    start_date DATETIME,
                    end_date DATETIME,
                    is_active_record BOOLEAN DEFAULT 1,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
            conn.commit()
            print("Table 'afk_history' created successfully.")

        conn.close()
    except Exception as e:
        print(f"Migration error: {e}")


if __name__ == "__main__":
    migrate()
