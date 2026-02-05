import logging

import aiosqlite

# Use the same DB as the rest of the app
DB_NAME = "guild_bot.db"

# --- NICKNAME VALIDATION ---

async def check_nickname_exists(nickname: str) -> bool:
    """
    Checks if a nickname exists in the 'players' table.
    Case-insensitive check.
    """
    if not nickname:
        return False
        
    async with aiosqlite.connect(DB_NAME) as conn:
        # We check locally in the players table (populated by parser)
        cursor = await conn.execute("SELECT 1 FROM players WHERE LOWER(nickname) = LOWER(?)", (nickname,))
        row = await cursor.fetchone()
        return row is not None

# Alias for compatibility with existing code, but updated logic
check_google_sheet = check_nickname_exists

# --- LOGGING (OPtional wrapper or remove) ---

async def log_reward_to_sheet(queue_name: str, main_nick: str, char_nick: str, manager_name: str, status: str = "Выдано"):
    """
    Legacy function stub. 
    Logging is now handled by RewardHistory in the database.
    This function processes nothing relative to Google Sheets.
    """
    logging.info(f"Reward Log: {queue_name} | {main_nick} ({char_nick}) | By: {manager_name} | Status: {status}")
    # We could potentially add extra DB logging here if needed, but RewardHistory covers the basics.
    return True
