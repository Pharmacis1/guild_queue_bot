import os
import pytz
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    exit("Error: BOT_TOKEN not found in .env file")

# Часовой пояс
MSK = pytz.timezone('Europe/Moscow')

# Инициализация
bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=MSK)