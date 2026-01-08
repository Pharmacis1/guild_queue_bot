import logging
import asyncio
import os
from dotenv import load_dotenv  # Библиотека для чтения .env
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import aiosqlite

# --- LOADING CONFIGURATION ---
# Загружаем переменные из файла .env
load_dotenv()

API_TOKEN = os.getenv("BOT_TOKEN")
DB_NAME = os.getenv("DB_NAME", "guild_bot.db") # Если в env нет имени, будет guild_bot.db

# Проверка, что токен загрузился
if not API_TOKEN:
    exit("Error: BOT_TOKEN not found in .env file")

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- STATES (Машина состояний) ---
class Registration(StatesGroup):
    waiting_for_main_nickname = State()
    waiting_for_alt_nickname = State()
    waiting_for_queue_selection = State()

# --- DATABASE SETUP ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            nickname TEXT UNIQUE,
            type TEXT, 
            telegram_username TEXT
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS queues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            queue_name TEXT,
            description TEXT
        )''')
        await db.commit()

# --- MOCK FUNCTIONS ---
async def check_google_sheet(nickname: str) -> bool:
    # Здесь в будущем будет подключение к Google Sheets API
    # Пока заглушка для тестов
    print(f"Checking Google Sheet for {nickname}...")
    if nickname.lower() in ['player1', 'superman', 'nagibator']:
        return True
    return False

# --- KEYBOARDS ---
def main_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👥 Мои персонажи"), KeyboardButton(text="📜 Очереди")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ], resize_keyboard=True)

def char_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Добавить основу"), KeyboardButton(text="➕ Добавить твина")],
        [KeyboardButton(text="📋 Список моих чaров"), KeyboardButton(text="🗑 Удалить твина")],
        [KeyboardButton(text="⬅️ Назад")]
    ], resize_keyboard=True)

# --- HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я бот для записи в очереди гильдии.", reply_markup=main_menu_kb())

@dp.message(F.text == "👥 Мои персонажи")
async def char_menu(message: types.Message):
    await message.answer("Меню управления персонажами:", reply_markup=char_menu_kb())

@dp.message(F.text == "➕ Добавить основу")
async def add_main_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT nickname FROM characters WHERE user_id = ? AND type = 'main'", (user_id,))
        existing = await cursor.fetchone()
        
        if existing:
            await message.answer(f"У тебя уже есть основа: {existing[0]}.")
        else:
            await message.answer("Введи никнейм своей основы (как в игре):")
            
    await state.set_state(Registration.waiting_for_main_nickname)

@dp.message(Registration.waiting_for_main_nickname)
async def process_main_nickname(message: types.Message, state: FSMContext):
    nickname = message.text.strip()
    user_id = message.from_user.id
    username = message.from_user.username

    is_in_guild = await check_google_sheet(nickname)
    
    if not is_in_guild:
        await message.answer("❌ Этот ник не найден в списке ГИ. Проверь написание.")
        await state.clear()
        return

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM characters WHERE nickname = ?", (nickname,))
        taken = await cursor.fetchone()
        
        if taken and taken[0] != user_id:
            await message.answer("⛔️ Этот никнейм уже занят другим пользователем!")
        else:
            await db.execute("INSERT OR REPLACE INTO characters (user_id, nickname, type, telegram_username) VALUES (?, ?, 'main', ?)", 
                             (user_id, nickname, username))
            await db.commit()
            await message.answer(f"✅ Основа **{nickname}** успешно привязана!", parse_mode="Markdown")
            
    await state.clear()

@dp.message(F.text == "⬅️ Назад")
async def go_back(message: types.Message):
    await message.answer("Главное меню", reply_markup=main_menu_kb())

# --- MAIN ENTRY POINT ---
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")