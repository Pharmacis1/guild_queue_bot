import asyncio
from aiogram import Bot
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("Error: BOT_TOKEN not found in .env")
        return

    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        print(f"BOT_USERNAME={me.username}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
