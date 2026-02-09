import sqlite3

db_name = "guild_bot.db"
conn = sqlite3.connect(db_name)
cursor = conn.cursor()

# Find user_id for 'BladeRNNR' or similar
cursor.execute("SELECT user_id FROM characters WHERE nickname LIKE '%Blade%' LIMIT 1")
uid_row = cursor.fetchone()
if uid_row:
    uid = uid_row[0]
    print(f"\nUser ID found: {uid}")
    
    print("\nLinked characters for this user:")
    cursor.execute("SELECT nickname FROM characters WHERE user_id = ?", (uid,))
    chars = [r[0] for r in cursor.fetchall()]
    for c in chars:
        print(f"Char in 'characters': {repr(c)} (len={len(c)})")
        # Try join with more detail
        cursor.execute("SELECT nickname, class_id FROM players WHERE LOWER(TRIM(nickname)) = LOWER(TRIM(?))", (c,))
        res = cursor.fetchone()
        if res:
            print(f"  Match in 'players': {repr(res[0])} (len={len(res[0])}) -> Class ID: {res[1]}")
        else:
            print(f"  NO MATCH in 'players' even with TRIM/LOWER.")
            # Search loosely
            search = f"%{c.strip()}%"
            cursor.execute("SELECT nickname FROM players WHERE nickname LIKE ?", (search,))
            loose = cursor.fetchall()
            if loose:
                print(f"  Loose matches: {[repr(l[0]) for l in loose]}")
else:
    print("User not found by nickname search.")

conn.close()
