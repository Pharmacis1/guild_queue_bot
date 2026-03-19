import logging

from sqlalchemy import func, select
from database import AsyncSessionLocal, Player

# --- NICKNAME VALIDATION ---


async def check_nickname_exists(nickname: str) -> bool:
    """
    Checks if a nickname exists in the 'players' table.
    Case-insensitive check.
    """
    if not nickname:
        return False

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Player).filter(func.lower(Player.nickname) == nickname.lower())
        )
        return result.scalar_one_or_none() is not None


# Alias for compatibility with existing code, but updated logic
check_google_sheet = check_nickname_exists

# --- LOGGING (OPtional wrapper or remove) ---


async def log_reward_to_sheet(
    queue_name: str, main_nick: str, char_nick: str, manager_name: str, status: str = "Выдано"
):
    """
    Legacy function stub.
    Logging is now handled by RewardHistory in the database.
    This function processes nothing relative to Google Sheets.
    """
    logging.info(f"Reward Log: {queue_name} | {main_nick} ({char_nick}) | By: {manager_name} | Status: {status}")
    # We could potentially add extra DB logging here if needed, but RewardHistory covers the basics.
    return True
