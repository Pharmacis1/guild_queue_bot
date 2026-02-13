import sqlite3
import os

DB_NAME = 'guild_bot.db'

def debug():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    nicks = ['AMONKNET', 'DarthMaul', 'Lumiya', 'Zannah', 'VisasMarr']
    
    print("--- PLAYERS ---")
    placeholders = ', '.join(['?'] * len(nicks))
    sql = f"SELECT nickname, role_id, user_id, is_alt, in_clan FROM players WHERE LOWER(nickname) IN ({placeholders})"
    params = [n.lower() for n in nicks]
    cur = conn.execute(sql, params)
    for r in cur:
        print(dict(r))
        
    print("\n--- CHARACTERS ---")
    sql = f"SELECT nickname, user_id, is_main FROM characters WHERE LOWER(nickname) IN ({placeholders})"
    cur = conn.execute(sql, params)
    for r in cur:
        print(dict(r))

    # Check if there's a user for the user_id found
    uids = set()
    cur = conn.execute(f"SELECT user_id FROM characters WHERE LOWER(nickname) IN ({placeholders})", params)
    for r in cur:
        if r['user_id']: uids.add(r['user_id'])
    
    if uids:
        print("\n--- USERS ---")
        placeholders_u = ', '.join(['?'] * len(uids))
        sql = f"SELECT id, telegram_id, username FROM users WHERE id IN ({placeholders_u})"
        cur = conn.execute(sql, list(uids))
        for r in cur:
            print(dict(r))

    conn.close()

if __name__ == "__main__":
    debug()
