import asyncio
import logging
import os
from datetime import datetime
import pytz # Библиотека часовых поясов

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.base import JobLookupError

# Импорт наших модулей
from database import *
from utils import check_google_sheet

# --- КОНФИГУРАЦИЯ ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    exit("Error: BOT_TOKEN not found in .env file")

# Настраиваем Московское время
MSK = pytz.timezone('Europe/Moscow')

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Инициализируем планировщик СРАЗУ с московским часовым поясом
scheduler = AsyncIOScheduler(timezone=MSK)

# Инициализация БД
init_db()

# --- СОСТОЯНИЯ (FSM) ---
class Registration(StatesGroup):
    waiting_for_main_nickname = State()
    waiting_for_alt_nickname = State()

class EditQueueStates(StatesGroup):
    waiting_for_new_description = State()

class MasterManageStates(StatesGroup):
    waiting_for_nickname_add = State()
    waiting_for_queue_add = State()

class AnnounceStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_type = State()
    waiting_for_datetime = State() # Для разового в будущем
    waiting_for_time_only = State() # Для ежедневного/еженедельного
    waiting_for_days = State() # Выбор дней недели

class LimitStates(StatesGroup):
    waiting_for_global_limit = State()
    waiting_for_nick_limit = State()
    waiting_for_personal_limit_value = State()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def ensure_user(telegram_id, username):
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        is_first = session.query(User).count() == 0
        user = User(telegram_id=telegram_id, username=username, is_master=is_first)
        session.add(user)
        session.commit()
    return user

def is_master(telegram_id):
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    return user and user.is_master

async def setup_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="/start", description="🏠 Главное меню"),
    ]
    await bot.set_my_commands(commands)

def get_effective_limit(user_id):
    """Считает актуальный лимит для юзера (Личный или Общий)"""
    # 1. Проверяем личный лимит
    user = session.get(User, user_id)
    if user.personal_limit is not None:
        return user.personal_limit
        
    # 2. Если личного нет, берем глобальный из настроек
    setting = session.query(Settings).filter_by(key="default_limit").first()
    return int(setting.value) if setting else 1

# --- КЛАВИАТУРЫ (INLINE) ---

def get_main_menu(user):
    kb = [
        [types.InlineKeyboardButton(text="👥 Мои персонажи", callback_data="menu_chars"),
         types.InlineKeyboardButton(text="✍️ Записаться в очередь", callback_data="menu_join")],
        [types.InlineKeyboardButton(text="📜 Моя история", callback_data="menu_history"),
         types.InlineKeyboardButton(text="ℹ️ Инфо об очередях", callback_data="menu_info")],
        [types.InlineKeyboardButton(text="🏃 Мои очереди", callback_data="my_active_queues")]
    ]
    if user.is_master:
        kb.append([types.InlineKeyboardButton(text="👑 Панель Мастера", callback_data="menu_master")])
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def get_master_menu():
    kb = [
        [types.InlineKeyboardButton(text="🎁 Выдать награды", callback_data="m_distribute"),
         types.InlineKeyboardButton(text="⚙️ Лимиты очередей", callback_data="m_limits_menu")],
         
        # НОВАЯ КНОПКА ЗДЕСЬ
        [types.InlineKeyboardButton(text="🔒 Блокировка очередей", callback_data="m_lock_menu")],
        
        [types.InlineKeyboardButton(text="✏️ Ред. описание", callback_data="m_edit_desc"),
         types.InlineKeyboardButton(text="🗓 Расписание", callback_data="m_schedule")],
         
        [types.InlineKeyboardButton(text="📢 Объявление", callback_data="m_announce")],
        
        [types.InlineKeyboardButton(text="➕ Force Add", callback_data="m_force_add"),
         types.InlineKeyboardButton(text="❌ Force Del", callback_data="m_force_del")],
         
        [types.InlineKeyboardButton(text="📜 Общий Архив", callback_data="m_global_log"),
         types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def get_back_btn(callback_data="back_to_main"):
    return types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]])

# Клавиатура выбора дней недели
def get_weekdays_kb(selected_days=None):
    if selected_days is None: selected_days = []
    
    # Коды дней для APScheduler
    days = [("Понедельник", "mon"), ("Вторник", "tue"), ("Среда", "wed"), 
            ("Четверг", "thu"), ("Пятница", "fri"), ("Суббота", "sat"), ("Воскресенье", "sun")]
    
    kb = []
    for name, code in days:
        # Если день выбран, ставим галочку
        mark = "✅" if code in selected_days else "⬜"
        kb.append([types.InlineKeyboardButton(text=f"{mark} {name}", callback_data=f"toggle_day_{code}")])
    
    # Кнопка Готово
    kb.append([types.InlineKeyboardButton(text="💾 Готово / Далее", callback_data="days_confirm")])
    return types.InlineKeyboardMarkup(inline_keyboard=kb)


# --- ОБРАБОТЧИКИ: СТАРТ И МЕНЮ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = ensure_user(message.from_user.id, message.from_user.username)
    await message.answer("👋 **Добро пожаловать в Guild Bot!**\nВыберите действие:", 
                         reply_markup=get_main_menu(user), parse_mode="Markdown")

@dp.callback_query(F.data == "back_to_main")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    try:
        await callback.message.edit_text("🏠 **Главное меню:**", reply_markup=get_main_menu(user), parse_mode="Markdown")
    except:
        await callback.message.answer("🏠 **Главное меню:**", reply_markup=get_main_menu(user), parse_mode="Markdown")


# --- 1. УПРАВЛЕНИЕ ПЕРСОНАЖАМИ ---
@dp.callback_query(F.data == "menu_chars")
async def chars_menu(callback: types.CallbackQuery):
    kb = [
        [types.InlineKeyboardButton(text="➕ Изменить Основу", callback_data="add_main")],
        [types.InlineKeyboardButton(text="➕ Добавить Твина", callback_data="add_alt")],
        [types.InlineKeyboardButton(text="📋 Список моих чаров", callback_data="list_chars")],
        [types.InlineKeyboardButton(text="🗑 Удалить Твина", callback_data="del_alt_menu")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ]
    await callback.message.edit_text("⚙️ **Управление персонажами:**", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@dp.callback_query(F.data == "add_main")
async def add_main_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✍️ Введите никнейм **ОСНОВЫ**:", reply_markup=get_back_btn("menu_chars"), parse_mode="Markdown")
    await state.set_state(Registration.waiting_for_main_nickname)

@dp.message(Registration.waiting_for_main_nickname)
async def process_main(message: types.Message, state: FSMContext):
    nick = message.text.strip()
    if not await check_google_sheet(nick): return await message.answer("❌ Ник не найден в гильдии.")
    user = ensure_user(message.from_user.id, message.from_user.username)
    old_main = session.query(Character).filter_by(user_id=user.id, is_main=True).first()
    if old_main: session.delete(old_main)
    session.add(Character(user_id=user.id, nickname=nick, is_main=True))
    session.commit()
    await message.answer(f"✅ Основа: <b>{nick}</b>", parse_mode="HTML", reply_markup=get_main_menu(user))
    await state.clear()

@dp.callback_query(F.data == "add_alt")
async def add_alt_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✍️ Введите никнейм **ТВИНА**:", reply_markup=get_back_btn("menu_chars"), parse_mode="Markdown")
    await state.set_state(Registration.waiting_for_alt_nickname)

@dp.message(Registration.waiting_for_alt_nickname)
async def process_alt(message: types.Message, state: FSMContext):
    nick = message.text.strip()
    if not await check_google_sheet(nick): return await message.answer("❌ Ник не найден.")
    user = ensure_user(message.from_user.id, message.from_user.username)
    if session.query(Character).filter_by(user_id=user.id, nickname=nick).first():
        return await message.answer("Уже добавлен.")
    session.add(Character(user_id=user.id, nickname=nick, is_main=False))
    session.commit()
    await message.answer(f"✅ Твин добавлен: <b>{nick}</b>", parse_mode="HTML", reply_markup=get_main_menu(user))
    await state.clear()

@dp.callback_query(F.data == "list_chars")
async def list_chars(callback: types.CallbackQuery):
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    chars = session.query(Character).filter_by(user_id=user.id).all()
    text = "🧙‍♂️ <b>Ваши персонажи:</b>\n"
    if not chars: text += "Список пуст."
    for c in chars:
        role = "👑" if c.is_main else "👤"
        text += f"{role} {c.nickname}\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_btn("menu_chars"))

@dp.callback_query(F.data == "del_alt_menu")
async def del_alt_menu(callback: types.CallbackQuery):
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    alts = session.query(Character).filter_by(user_id=user.id, is_main=False).all()
    if not alts: return await callback.answer("Нет твинов.", show_alert=True)
    kb = [[types.InlineKeyboardButton(text=f"❌ {c.nickname}", callback_data=f"del_c_{c.id}")] for c in alts]
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_chars")])
    await callback.message.edit_text("Кого удалить?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("del_c_"))
async def del_char_action(callback: types.CallbackQuery):
    cid = int(callback.data.split("_")[2])
    char = session.get(Character, cid)
    if char:
        session.delete(char)
        session.commit()
        await callback.answer("Удалено.")
        await del_alt_menu(callback)


# --- 2. ОЧЕРЕДИ ---
@dp.callback_query(F.data == "menu_join")
async def join_menu(callback: types.CallbackQuery):
    # Берем только активные (не удаленные) очереди
    queues = session.query(QueueType).filter_by(is_active=True).all()
    kb = []
    
    for q in queues:
        count = session.query(QueueEntry).filter_by(queue_type_id=q.id).count()
        
        # Если закрыта - добавляем значок замка
        status = "🔒 ЗАКРЫТА" if q.is_locked else f"({count})"
        
        kb.append([types.InlineKeyboardButton(text=f"{q.name} {status}", callback_data=f"view_q_{q.id}")])
        
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    
    await callback.message.edit_text(
        "✍️ <b>Выберите очередь:</b>\n(🔒 = запись временно закрыта)", 
        parse_mode="HTML", 
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data.startswith("view_q_"))
async def view_queue(callback: types.CallbackQuery):
    qid = int(callback.data.split("_")[2])
    q = session.get(QueueType, qid)
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    entries = session.query(QueueEntry).filter_by(queue_type_id=qid).all()
    
    text = f"🛡 <b>Очередь: {q.name}</b>\n\n"
    if not entries: text += "<i>Пока пусто.</i>"
    else:
        for i, e in enumerate(entries, 1):
            text += f"{i}. {e.character_name}\n"
    
    kb = []
    user_entry = session.query(QueueEntry).filter_by(queue_type_id=qid, user_id=user.id).first()
    if user_entry: kb.append([types.InlineKeyboardButton(text="🏃 Выйти из очереди", callback_data=f"leave_q_{qid}")])
    else: kb.append([types.InlineKeyboardButton(text="✍️ Записаться", callback_data=f"pre_join_{qid}")])
    kb.append([types.InlineKeyboardButton(text="🔙 К списку", callback_data="menu_join")])
    
    try: await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    except: pass

@dp.callback_query(F.data.startswith("pre_join_"))
async def pre_join(callback: types.CallbackQuery):
    qid = int(callback.data.split("_")[2])
    q = session.get(QueueType, qid)
    
    # ПРОВЕРКА НА БЛОКИРОВКУ
    if q.is_locked:
        return await callback.answer("⛔ Очередь временно закрыта Мастером!", show_alert=True)
        
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    chars = session.query(Character).filter_by(user_id=user.id).all()
    
    if not chars: return await callback.answer("Нет персонажей!", show_alert=True)
    
    kb = [[types.InlineKeyboardButton(text=f"{'👑' if c.is_main else '👤'} {c.nickname}", callback_data=f"do_join_{qid}_{c.id}")] for c in chars]
    kb.append([types.InlineKeyboardButton(text="🔙 Отмена", callback_data=f"view_q_{qid}")])
    await callback.message.edit_text("Кем записаться?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("do_join_"))
async def do_join(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    qid, cid = int(parts[2]), int(parts[3])
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    char = session.get(Character, cid)
    
    if not char: return await callback.answer("Ошибка чара.", show_alert=True)
    
    existing = session.query(QueueEntry).filter_by(queue_type_id=qid, user_id=user.id).first()
    if existing: return await callback.answer("Вы уже в очереди.", show_alert=True)
    
    # --- НОВАЯ ЛОГИКА ПРОВЕРКИ ЛИМИТА ---
    limit = get_effective_limit(user.id)
    current_count = session.query(QueueEntry).filter_by(user_id=user.id).count()
    
    if current_count >= limit:
        return await callback.answer(f"⛔ Лимит записей исчерпан! ({current_count}/{limit})", show_alert=True)
    # ------------------------------------
    
    session.add(QueueEntry(user_id=user.id, queue_type_id=qid, character_name=char.nickname))
    session.commit()
    await callback.answer(f"Записан: {char.nickname}")
    await view_queue(callback)

@dp.callback_query(F.data.startswith("leave_q_"))
async def leave_queue(callback: types.CallbackQuery):
    qid = int(callback.data.split("_")[2])
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    entry = session.query(QueueEntry).filter_by(queue_type_id=qid, user_id=user.id).first()
    if entry:
        session.delete(entry)
        session.commit()
        await callback.answer("Вы вышли.")
    await view_queue(callback)

@dp.callback_query(F.data == "my_active_queues")
async def show_my_active_queues(callback: types.CallbackQuery):
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    entries = session.query(QueueEntry).filter_by(user_id=user.id).all()
    if not entries: return await callback.message.edit_text("📭 <b>Нет активных записей.</b>", parse_mode="HTML", reply_markup=get_back_btn())
    text = "🏃 <b>Вы записаны:</b>\n\n"
    kb = []
    for e in entries:
        text += f"🔹 <b>{e.queue.name}</b> — {e.character_name}\n"
        kb.append([types.InlineKeyboardButton(text=f"❌ Выйти: {e.queue.name}", callback_data=f"leave_q_{e.queue_type_id}")])
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))


# --- 3. ИНФО И ИСТОРИЯ ---
@dp.callback_query(F.data == "menu_history")
async def my_history(callback: types.CallbackQuery):
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    hist = session.query(RewardHistory).filter_by(user_id=user.id).order_by(RewardHistory.timestamp.desc()).limit(10).all()
    text = "📜 <b>История наград:</b>\n"
    if not hist: text += "<i>Пусто</i>"
    for h in hist: text += f"🔹 {h.timestamp.strftime('%d.%m')} — {h.queue_name} ({h.character_name})\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_btn())

@dp.callback_query(F.data == "menu_info")
async def info_queues(callback: types.CallbackQuery):
    queues = session.query(QueueType).filter_by(is_active=True).all()
    text = "ℹ️ <b>Справка:</b>\n\n"
    for q in queues: text += f"🔹 <b>{q.name}</b>\n{q.description}\n\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_btn())


# --- 4. ПАНЕЛЬ МАСТЕРА ---
@dp.callback_query(F.data == "menu_master")
async def master_menu(callback: types.CallbackQuery):
    if not is_master(callback.from_user.id): return
    await callback.message.edit_text("👑 **Панель Мастера**", reply_markup=get_master_menu(), parse_mode="Markdown")

# Раздача наград
@dp.callback_query(F.data == "m_distribute")
async def m_dist_start(callback: types.CallbackQuery):
    queues = session.query(QueueType).all()
    kb = [[types.InlineKeyboardButton(text=f"{q.name}", callback_data=f"dist_{q.id}")] for q in queues]
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text("🎁 Что раздаем?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("dist_"))
async def m_show_dist_list(callback: types.CallbackQuery):
    try: qid = int(callback.data.split("_")[1])
    except: return await callback.answer("Ошибка навигации.", show_alert=True)
    
    q = session.get(QueueType, qid)
    entries = session.query(QueueEntry).filter_by(queue_type_id=qid).all()
    
    if not entries:
        return await callback.message.edit_text(
            f"✅ Очередь <b>{q.name}</b> пуста.", 
            parse_mode="HTML", 
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 Назад", callback_data="m_distribute")]])
        )
    
    # 1. Формируем список ников для копирования
    # Используем тег <code>, чтобы в Телеграме текст копировался по клику
    nick_list = "\n".join([e.character_name for e in entries])
    
    text = (f"🎁 <b>Раздача: {q.name}</b>\n\n"
            f"Список для копирования:\n"
            f"<code>{nick_list}</code>\n\n"
            f"👇 Нажмите на кнопку, чтобы выдать награду:")
    
    # 2. Формируем кнопки
    kb = [[types.InlineKeyboardButton(text=f"💰 {e.character_name}", callback_data=f"issue_{e.id}")] for e in entries]
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="m_distribute")])
    
    await callback.message.edit_text(
        text, 
        parse_mode="HTML", 
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data.startswith("issue_"))
async def m_issue_reward(callback: types.CallbackQuery):
    eid = int(callback.data.split("_")[1])
    entry = session.get(QueueEntry, eid)
    if not entry: return await callback.answer("Уже выдано.", show_alert=True)
    
    qid = entry.queue_type_id
    q_name, c_name = entry.queue.name, entry.character_name
    master = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
    
    session.add(RewardHistory(user_id=entry.user_id, character_name=c_name, queue_name=q_name, issued_by=master.username))
    try:
        u = session.get(User, entry.user_id)
        kb = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔄 Записаться снова", callback_data=f"pre_join_{qid}")],[types.InlineKeyboardButton(text="📋 Другая очередь", callback_data="menu_join")]])
        await bot.send_message(u.telegram_id, f"🎉 <b>Награда:</b> {q_name} ({c_name})\nЧто дальше?", parse_mode="HTML", reply_markup=kb)
    except: pass
    
    session.delete(entry)
    session.commit()
    await callback.answer(f"✅ Выдано: {c_name}")
    callback.data = f"dist_{qid}"
    await m_show_dist_list(callback)

# Ред. описание
@dp.callback_query(F.data == "m_edit_desc")
async def m_edit_start(callback: types.CallbackQuery):
    queues = session.query(QueueType).all()
    kb = [[types.InlineKeyboardButton(text=f"{q.name}", callback_data=f"edit_d_{q.id}")] for q in queues]
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text("✏️ Выберите очередь:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("edit_d_"))
async def m_edit_input(callback: types.CallbackQuery, state: FSMContext):
    qid = int(callback.data.split("_")[2])
    q = session.get(QueueType, qid)
    await state.update_data(qid=qid)
    await callback.message.edit_text(
        f"Текущее: {q.description}\n\n👇 **Введите новое описание:**", 
        parse_mode="Markdown",
        reply_markup=get_back_btn("menu_master") # <--- КНОПКА
    )
    await state.set_state(EditQueueStates.waiting_for_new_description)

@dp.message(EditQueueStates.waiting_for_new_description)
async def m_edit_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    q = session.get(QueueType, data['qid'])
    q.description = message.text
    session.commit()
    await message.answer("✅ Сохранено.", reply_markup=get_master_menu())
    await state.clear()

# Force Actions
@dp.callback_query(F.data == "m_force_add")
async def m_force_add(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "➕ Введите никнейм для принудительной записи:", 
        parse_mode="Markdown",
        reply_markup=get_back_btn("menu_master") # <--- КНОПКА
    )
    await state.set_state(MasterManageStates.waiting_for_nickname_add)

@dp.message(MasterManageStates.waiting_for_nickname_add)
async def m_force_nick(message: types.Message, state: FSMContext):
    nick = message.text.strip()
    if not await check_google_sheet(nick): return await message.answer("❌ Невалидный ник.")
    await state.update_data(nick=nick)
    queues = session.query(QueueType).all()
    kb = [[types.InlineKeyboardButton(text=q.name, callback_data=f"f_add_{q.id}")] for q in queues]
    await message.answer("Куда?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(MasterManageStates.waiting_for_queue_add)

@dp.callback_query(F.data.startswith("f_add_"))
async def m_force_add_final(callback: types.CallbackQuery, state: FSMContext):
    qid = int(callback.data.split("_")[2])
    data = await state.get_data()
    nick = data['nick']
    char = session.query(Character).filter_by(nickname=nick).first()
    uid = char.user_id if char else session.query(User).filter_by(telegram_id=callback.from_user.id).first().id
    session.add(QueueEntry(user_id=uid, queue_type_id=qid, character_name=nick))
    session.commit()
    await callback.message.edit_text(f"✅ {nick} добавлен.", reply_markup=get_master_menu())
    await state.clear()

@dp.callback_query(F.data == "m_force_del")
async def m_force_del(callback: types.CallbackQuery):
    queues = session.query(QueueType).all()
    kb = []
    for q in queues:
        count = session.query(QueueEntry).filter_by(queue_type_id=q.id).count()
        if count > 0: kb.append([types.InlineKeyboardButton(text=f"{q.name} ({count})", callback_data=f"sel_del_{q.id}")])
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text("❌ Выберите очередь:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("sel_del_"))
async def m_force_del_list(callback: types.CallbackQuery):
    qid = int(callback.data.split("_")[2])
    entries = session.query(QueueEntry).filter_by(queue_type_id=qid).all()
    kb = [[types.InlineKeyboardButton(text=f"❌ {e.character_name}", callback_data=f"kill_{e.id}")] for e in entries]
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text("Кого удалить?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("kill_"))
async def m_kill(callback: types.CallbackQuery):
    eid = int(callback.data.split("_")[1])
    e = session.get(QueueEntry, eid)
    
    if e:
        # 1. Запоминаем ID очереди перед удалением
        qid = e.queue_type_id
        
        # 2. Удаляем запись
        session.delete(e)
        session.commit()
        await callback.answer("✅ Удалено.")
        
        # 3. Обновляем список (вместо удаления сообщения)
        # Подменяем данные колбэка, чтобы функция списка поняла, какую очередь показать
        callback.data = f"sel_del_{qid}"
        await m_force_del_list(callback)
        
    else:
        await callback.answer("Уже удален.", show_alert=True)
        # Если запись не найдена, просто удаляем сообщение (или можно вернуть в меню)
        await callback.message.delete()

@dp.callback_query(F.data == "m_global_log")
async def m_global_log(callback: types.CallbackQuery):
    # Загружаем последние 15 записей
    hist = session.query(RewardHistory).order_by(RewardHistory.timestamp.desc()).limit(15).all()
    
    text = "🗄 <b>Лог последних выдач:</b>\n\n"
    if not hist:
        text += "<i>Архив пуст.</i>"
        
    for h in hist:
        # Используем HTML, чтобы ники со спецсимволами не ломали бота
        date_str = h.timestamp.strftime('%d.%m')
        text += f"• <code>{date_str}</code> <b>{h.character_name}</b> → {h.queue_name}\n"
        
    await callback.message.edit_text(
        text, 
        parse_mode="HTML", 
        reply_markup=get_back_btn("menu_master")
    )

# --- УПРАВЛЕНИЕ ЛИМИТАМИ (LIMITS MANAGEMENT) ---

@dp.callback_query(F.data == "m_limits_menu")
async def m_limits_menu(callback: types.CallbackQuery):
    setting = session.query(Settings).filter_by(key="default_limit").first()
    g_limit = setting.value if setting else "1"
    
    text = (f"⚙️ <b>Настройки лимитов</b>\n"
            f"🌐 Общий лимит: <b>{g_limit}</b>")
            
    kb = [
        [types.InlineKeyboardButton(text=f"🌐 Изменить общий ({g_limit})", callback_data="m_set_global")],
        [types.InlineKeyboardButton(text="👤 Изменить личный лимит", callback_data="m_set_personal")],
        # НОВАЯ КНОПКА
        [types.InlineKeyboardButton(text="📋 Список индив. лимитов", callback_data="m_list_limits")], 
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")]
    ]
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

# НОВАЯ ФУНКЦИЯ: Показать всех с особыми правами
@dp.callback_query(F.data == "m_list_limits")
async def m_list_personal_limits(callback: types.CallbackQuery):
    # Ищем пользователей, у которых personal_limit НЕ None
    users = session.query(User).filter(User.personal_limit != None).all()
    
    if not users:
        text = "🤷‍♂️ <b>Индивидуальных лимитов нет.</b>\nВсе используют общий лимит."
    else:
        text = "📋 <b>Игроки с особыми лимитами:</b>\n\n"
        for u in users:
            # Пытаемся найти ник основы для красоты, иначе берем username телеграма
            main_char = session.query(Character).filter_by(user_id=u.id, is_main=True).first()
            display_name = main_char.nickname if main_char else (u.username or f"ID {u.telegram_id}")
            
            text += f"👤 <b>{display_name}</b>: {u.personal_limit} оч.\n"
            
    await callback.message.edit_text(
        text, 
        parse_mode="HTML", 
        reply_markup=get_back_btn("m_limits_menu")
    )

# 1. Глобальный лимит
@dp.callback_query(F.data == "m_set_global")
async def m_set_global_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🌐 Введите новое число для <b>ОБЩЕГО</b> лимита:", parse_mode="HTML", reply_markup=get_back_btn("m_limits_menu"))
    await state.set_state(LimitStates.waiting_for_global_limit)

@dp.message(LimitStates.waiting_for_global_limit)
async def m_set_global_save(message: types.Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        if val < 1: raise ValueError
        
        setting = session.query(Settings).filter_by(key="default_limit").first()
        setting.value = str(val)
        session.commit()
        
        await message.answer(f"✅ Общий лимит теперь: <b>{val}</b>", parse_mode="HTML", reply_markup=get_master_menu())
        await state.clear()
    except:
        await message.answer("❌ Введите целое число больше 0.", reply_markup=get_back_btn("m_limits_menu"))

# 2. Персональный лимит
@dp.callback_query(F.data == "m_set_personal")
async def m_set_personal_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("👤 Введите <b>никнейм</b> игрока (Основы или Твина):", parse_mode="HTML", reply_markup=get_back_btn("m_limits_menu"))
    await state.set_state(LimitStates.waiting_for_nick_limit)

@dp.message(LimitStates.waiting_for_nick_limit)
async def m_set_personal_nick(message: types.Message, state: FSMContext):
    nick = message.text.strip()
    # Ищем владельца этого ника
    char = session.query(Character).filter_by(nickname=nick).first()
    
    if not char:
        return await message.answer("❌ Персонаж не найден в базе бота. Пусть сначала добавит себя в 'Мои персонажи'.", reply_markup=get_back_btn("m_limits_menu"))
    
    user = session.get(User, char.user_id)
    current = user.personal_limit if user.personal_limit is not None else "Не задан (Общий)"
    
    await state.update_data(user_id=user.id, nick=nick)
    await message.answer(
        f"👤 Игрок: <b>{user.username}</b> (найден по {nick})\n"
        f"Текущий личный лимит: <b>{current}</b>\n\n"
        f"Введите новое число (или 0, чтобы сбросить на общий):", 
        parse_mode="HTML", 
        reply_markup=get_back_btn("m_limits_menu")
    )
    await state.set_state(LimitStates.waiting_for_personal_limit_value)

@dp.message(LimitStates.waiting_for_personal_limit_value)
async def m_set_personal_save(message: types.Message, state: FSMContext):
    try:
        val = int(message.text.strip())
        data = await state.get_data()
        user = session.get(User, data['user_id'])
        
        if val <= 0:
            user.personal_limit = None # Сброс
            msg = f"✅ Лимит для {data['nick']} сброшен на <b>Общий</b>."
        else:
            user.personal_limit = val
            msg = f"✅ Лимит для {data['nick']} установлен: <b>{val}</b>."
            
        session.commit()
        await message.answer(msg, parse_mode="HTML", reply_markup=get_master_menu())
        await state.clear()
    except:
        await message.answer("❌ Введите целое число.", reply_markup=get_back_btn("m_limits_menu"))

# --- БЛОКИРОВКА ОЧЕРЕДЕЙ (LOCKS) ---

@dp.callback_query(F.data == "m_lock_menu")
async def m_lock_menu(callback: types.CallbackQuery):
    queues = session.query(QueueType).filter_by(is_active=True).all()
    
    text = "🔒 <b>Управление доступом:</b>\nНажмите на очередь, чтобы Открыть/Закрыть её для записи."
    kb = []
    
    for q in queues:
        # Ставим визуальный индикатор
        status_icon = "🔴 ЗАКРЫТО" if q.is_locked else "🟢 ОТКРЫТО"
        kb.append([types.InlineKeyboardButton(
            text=f"{status_icon} {q.name}", 
            callback_data=f"toggle_lock_{q.id}"
        )])
        
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    
    await callback.message.edit_text(
        text, 
        parse_mode="HTML", 
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data.startswith("toggle_lock_"))
async def m_toggle_lock(callback: types.CallbackQuery):
    qid = int(callback.data.split("_")[2])
    q = session.get(QueueType, qid)
    
    # Переключаем статус (True -> False или False -> True)
    q.is_locked = not q.is_locked
    session.commit()
    
    status_text = "🔒 ЗАБЛОКИРОВАНА" if q.is_locked else "🟢 РАЗБЛОКИРОВАНА"
    await callback.answer(f"Очередь {q.name}: {status_text}")
    
    # Обновляем меню, чтобы перерисовались значки
    await m_lock_menu(callback)


# --- 5. НОВАЯ ЛОГИКА ОБЪЯВЛЕНИЙ (BROADCAST) ---

@dp.callback_query(F.data == "m_announce")
async def m_ann_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📢 Введите текст объявления:", 
        parse_mode="Markdown",
        # ДОБАВИЛИ КНОПКУ ОТМЕНЫ
        reply_markup=get_back_btn("menu_master")
    )
    await state.set_state(AnnounceStates.waiting_for_text)

@dp.message(AnnounceStates.waiting_for_text)
async def m_ann_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    kb = [
        [types.InlineKeyboardButton(text="⚡ Прямо сейчас", callback_data="ann_now")],
        [types.InlineKeyboardButton(text="📅 Разово в будущем", callback_data="ann_future")],
        [types.InlineKeyboardButton(text="⏰ Ежедневно", callback_data="ann_daily")],
        [types.InlineKeyboardButton(text="📆 По дням недели", callback_data="ann_weekly")]
    ]
    await message.answer("Когда отправить?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(AnnounceStates.waiting_for_type)

@dp.callback_query(F.data.startswith("ann_"))
async def m_ann_type(callback: types.CallbackQuery, state: FSMContext):
    atype = callback.data.split("_")[1]
    
    if atype == "now":
        # Отправка сразу
        data = await state.get_data()
        ann = ScheduledAnnouncement(text=data['text'], schedule_type='once_now', run_time='now', is_active=False)
        session.add(ann)
        session.commit()
        await run_broadcast(ann.id, callback.bot)
        await callback.message.edit_text("✅ Отправлено.", reply_markup=get_master_menu())
        await state.clear()
        

    elif atype == "future":
        # Разово в будущем
        await callback.message.edit_text(
            "📅 Введите дату и время (МСК) в формате:\n`ДД.ММ.ГГГГ ЧЧ:ММ`\nПример: 25.12.2024 14:00", 
            parse_mode="Markdown",
            reply_markup=get_back_btn("menu_master") # <--- КНОПКА
        )
        await state.set_state(AnnounceStates.waiting_for_datetime)
        
    elif atype == "daily":
        # Ежедневно
        await state.update_data(days=[]) 
        await callback.message.edit_text(
            "⏰ Введите время (МСК) в формате `ЧЧ:ММ`:", 
            parse_mode="Markdown",
            reply_markup=get_back_btn("menu_master") # <--- КНОПКА
        )
        await state.set_state(AnnounceStates.waiting_for_time_only)


    elif atype == "weekly":
        # Выбор дней недели
        await state.update_data(days=[]) # Инициализируем список
        await callback.message.edit_text("📆 Выберите дни недели:", reply_markup=get_weekdays_kb([]))
        await state.set_state(AnnounceStates.waiting_for_days)

# --- Обработка ввода даты/времени/дней ---

# 1. Разово в будущем (Дата + Время)
@dp.message(AnnounceStates.waiting_for_datetime)
async def process_future_datetime(message: types.Message, state: FSMContext):
    try:
        # Проверяем формат
        dt_str = message.text.strip()
        datetime.strptime(dt_str, "%d.%m.%Y %H:%M") # Валидация
        
        data = await state.get_data()
        ann = ScheduledAnnouncement(text=data['text'], schedule_type='once_future', run_time=dt_str, is_active=True)
        session.add(ann)
        session.commit()
        
        schedule_job(ann, message.bot)
        await message.answer(f"✅ Запланировано на {dt_str} (МСК)", reply_markup=get_master_menu())
        await state.clear()
    except ValueError:
        await message.answer("❌ Неверный формат. Нужно: ДД.ММ.ГГГГ ЧЧ:ММ")

# 2. Логика выбора дней недели (кнопки)
@dp.callback_query(F.data.startswith("toggle_day_"))
async def toggle_day(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split("_")[2]
    data = await state.get_data()
    days = data.get('days', [])
    
    if code in days: days.remove(code)
    else: days.append(code)
    
    await state.update_data(days=days)
    # Обновляем клавиатуру
    await callback.message.edit_reply_markup(reply_markup=get_weekdays_kb(days))

@dp.callback_query(F.data == "days_confirm")
async def confirm_days(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    days = data.get('days', [])
    if not days:
        return await callback.answer("Выберите хотя бы один день!", show_alert=True)
    
    await callback.message.edit_text(
        "⏰ Введите время (МСК) в формате `ЧЧ:ММ`:", 
        parse_mode="Markdown",
        reply_markup=get_back_btn("menu_master") # <--- КНОПКА
    )
    await state.set_state(AnnounceStates.waiting_for_time_only)

# 3. Финальное время для Daily/Weekly
@dp.message(AnnounceStates.waiting_for_time_only)
async def process_time_only(message: types.Message, state: FSMContext):
    try:
        time_str = message.text.strip()
        datetime.strptime(time_str, "%H:%M") # Валидация
        
        data = await state.get_data()
        days_list = data.get('days', []) # Если пусто - значит daily
        
        sch_type = 'weekly' if days_list else 'daily'
        days_str = ",".join(days_list) if days_list else None
        
        ann = ScheduledAnnouncement(
            text=data['text'], 
            schedule_type=sch_type, 
            run_time=time_str, 
            days_of_week=days_str, 
            is_active=True
        )
        session.add(ann)
        session.commit()
        
        schedule_job(ann, message.bot)
        await message.answer(f"✅ Расписание создано: {time_str} (МСК)", reply_markup=get_master_menu())
        await state.clear()
    except ValueError:
        await message.answer("❌ Неверный формат времени. Нужно ЧЧ:ММ")


# --- ЛОГИКА SCHEDULER (ПЛАНИРОВЩИК) ---

def schedule_job(ann, bot_instance):
    """Универсальная функция добавления задачи в планировщик"""
    job_id = f"ann_{ann.id}"
    
    try:
        if ann.schedule_type == 'daily':
            # Ежедневно
            h, m = map(int, ann.run_time.split(':'))
            scheduler.add_job(run_broadcast, 'cron', hour=h, minute=m, id=job_id, replace_existing=True, args=[ann.id, bot_instance])
            
        elif ann.schedule_type == 'weekly':
            # По дням недели
            h, m = map(int, ann.run_time.split(':'))
            scheduler.add_job(run_broadcast, 'cron', day_of_week=ann.days_of_week, hour=h, minute=m, id=job_id, replace_existing=True, args=[ann.id, bot_instance])
            
        elif ann.schedule_type == 'once_future':
            # Разово в будущем
            # Парсим дату как "naive", потом делаем её MSK
            dt = datetime.strptime(ann.run_time, "%d.%m.%Y %H:%M")
            # Локализуем её в Москву
            dt_msk = MSK.localize(dt)
            
            scheduler.add_job(run_broadcast, 'date', run_date=dt_msk, id=job_id, replace_existing=True, args=[ann.id, bot_instance])
            
    except Exception as e:
        print(f"❌ Ошибка планирования {job_id}: {e}")

async def run_broadcast(ann_id, bot_instance):
    print(f"📣 Broadcast {ann_id} started...")
    with session.no_autoflush:
        ann = session.get(ScheduledAnnouncement, ann_id)
        if not ann or not ann.is_active: return

        users = session.query(User).join(Character).distinct().all()
        count = 0
        for u in users:
            try:
                await bot_instance.send_message(u.telegram_id, f"📢 <b>ОБЪЯВЛЕНИЕ</b>\n\n{ann.text}", parse_mode="HTML")
                count += 1
            except: pass
        
        print(f"✅ Broadcast done. Sent to {count}.")
        
        # Если это разовая задача - выключаем её после выполнения
        if ann.schedule_type == 'once_future':
            ann.is_active = False
            session.commit()

# --- УПРАВЛЕНИЕ РАСПИСАНИЕМ ---
@dp.callback_query(F.data == "m_schedule")
async def m_show_schedule(callback: types.CallbackQuery):
    tasks = session.query(ScheduledAnnouncement).filter_by(is_active=True).all()
    if not tasks: return await callback.message.edit_text("📭 Пусто.", parse_mode="HTML", reply_markup=get_back_btn("menu_master"))
    
    text = "🗓 <b>Активные задачи:</b>\n\n"
    kb = []
    for t in tasks:
        desc = ""
        if t.schedule_type == 'daily': desc = "⏰ Ежедневно"
        elif t.schedule_type == 'weekly': desc = f"📆 {t.days_of_week}"
        elif t.schedule_type == 'once_future': desc = f"📅 {t.run_time}"
        else: continue # once_now не храним в активных
        
        preview = t.text[:15] + "..."
        text += f"{desc} в {t.run_time} — {preview}\n"
        kb.append([types.InlineKeyboardButton(text=f"❌ Удалить ({desc})", callback_data=f"del_sch_{t.id}")])
        
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("del_sch_"))
async def m_del_schedule(callback: types.CallbackQuery):
    aid = int(callback.data.split("_")[2])
    task = session.get(ScheduledAnnouncement, aid)
    if task:
        task.is_active = False
        session.commit()
        try: scheduler.remove_job(f"ann_{aid}")
        except JobLookupError: pass
        await callback.answer("Отключено.")
        await m_show_schedule(callback)
    else: await m_show_schedule(callback)

# --- ЗАПУСК ---
async def on_startup():
    await setup_bot_commands(bot)
    # Восстановление
    tasks = session.query(ScheduledAnnouncement).filter_by(is_active=True).all()
    count = 0
    for t in tasks:
        if t.schedule_type != 'once_now':
            schedule_job(t, bot)
            count += 1
    scheduler.start()
    print(f"✅ Bot started (Timezone: MSK). Jobs restored: {count}")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try: asyncio.run(main())
    except: pass