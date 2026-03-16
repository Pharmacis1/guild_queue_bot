import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

def clean_afk(db_name):
    try:
        db = sqlite3.connect(db_name)
        cur = db.cursor()
        cur.execute("SELECT user_id FROM characters WHERE nickname=?", ('ㄒhｅ乇ηD',))
        rows = cur.fetchall()
        
        if rows:
            for row in rows:
                uid = row[0]
                cur.execute("UPDATE users SET afk_start=NULL, afk_end=NULL, afk_reason=NULL WHERE id=?", (uid,))
            db.commit()
            print(f"[{db_name}] Cleaned AFK for user_id(s) {[r[0] for r in rows]} (Player: ㄒhｅ乇ηD)")
        else:
            # Maybe the player name is stored directly in players, but afk is via user_id
            print(f"[{db_name}] Nickname 'ㄒhｅ乇ηD' not found in characters.")
            
        # Check players table
        cur.execute("SELECT role_id, user_id FROM players WHERE nickname=?", ('ㄒhｅ乇ηD',))
        p_row = cur.fetchone()
        if p_row:
            print(f"[{db_name}] Found in players table: role_id={p_row[0]}, user_id={p_row[1]}")
            
    except sqlite3.OperationalError as e:
        print(f"[{db_name}] Error: {e}")
    finally:
        db.close()

clean_afk('guild_bot.db')
clean_afk('guild_bot_2026-03-12_07-49-29_manual_user.db')
