import sqlite3
for db in ['guild_bot.db', 'guild_bot_2026-03-12_07-49-29_manual_user.db']:
    conn = sqlite3.connect(db)
    conn.execute("UPDATE users SET afk_start = NULL, afk_end = NULL, afk_reason = NULL WHERE id = 8")
    conn.commit()
    conn.close()
    print("Cleared AFK in", db)
