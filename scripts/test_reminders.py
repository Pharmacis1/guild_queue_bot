import asyncio
import os
import logging
from dotenv import load_dotenv
from aiogram import Bot

from database import init_db
from logic.reminders import send_db_upload_reminder

async def test():
    load_dotenv()
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        print("No BOT_TOKEN")
        return

    init_db()
    bot = Bot(token=TOKEN)

    try:
        print("Running send_db_upload_reminder...")
        await send_db_upload_reminder(bot, 14.5)
        print("Done.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await bot.session.close()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test())
