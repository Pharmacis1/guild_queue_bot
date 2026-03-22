import os
import asyncio
from aiogram import Bot
from dotenv import load_dotenv

async def check():
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("No token")
        return
    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        print(f"Bot is alive: @{me.username}")
    except Exception as e:
        print(f"Error connecting to Telegram: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(check())
