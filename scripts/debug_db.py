import sqlite3

DB_NAME = "guild_bot.db"

def check_db():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        print("--- Checking Players ---")
        cursor.execute("SELECT COUNT(*) FROM players")
        total = cursor.fetchone()
        print(f"Total players: {total[0]}")

        cursor.execute("SELECT COUNT(*) FROM players WHERE in_clan = 1")
        in_clan = cursor.fetchone()
        print(f"Players in_clan=1: {in_clan[0]}")

        print("\n--- Testing Query ---")
        start_date = "2026-01-26"
        end_date = "2026-02-01"
        
        sql = """
            SELECT 
                p.role_id, 
                COALESCE(p.nickname, 'ID ' || p.role_id), 
                p.class_id,
                e.timestamp, 
                e.value, 
                e.event_type
            FROM players p
            LEFT JOIN events e ON p.role_id = e.role_id 
                AND e.event_type IN (1, 2)
                AND substr(e.event_date, 1, 10) >= ? 
                AND substr(e.event_date, 1, 10) <= ?
            WHERE p.in_clan = 1
            LIMIT 5
        """
        cursor.execute(sql, (start_date, end_date))
        rows = cursor.fetchall()
        print(f"Query returned {len(rows)} rows (limit 5)")
        for r in rows:
            print(r)
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_db()
