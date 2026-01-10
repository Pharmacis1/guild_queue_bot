import math
import asyncio
from datetime import datetime
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from apscheduler.jobstores.base import JobLookupError

# Импорты из других файлов проекта
from loader import bot, scheduler, MSK
from database import session, User, Character, QueueEntry, QueueType, RewardHistory, ScheduledAnnouncement, Settings
from keyboards import get_master_menu, get_back_btn, get_weekdays_kb
from states import MasterManageStates, EditQueueStates, AnnounceStates, LimitStates
from utils import check_google_sheet, log_reward_to_sheet

router = Router()
PAGE_SIZE = 10

# Проверка на мастера
def is_master(telegram_id):
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    return user and user.is_master

# --- ПАНЕЛЬ МАСТЕРА ---
@router.callback_query(F.data == "menu_master")
async def master_menu(callback: types.CallbackQuery):
    if not is_master(callback.from_user.id): return
    await callback.message.edit_text("👑 **Панель Мастера**", reply_markup=get_master_menu(), parse_mode="Markdown")

# --- УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ---
@router.callback_query(F.data.startswith("m_users_list"))
async def m_users_list(callback: types.CallbackQuery):
    try:
        page = int(callback.data.split(":")[1])
    except:
        page = 0

    users = session.query(User).join(Character).distinct().all()
    
    if not users:
        return await callback.message.edit_text("🤷‍♂️ В базе пока нет игроков с персонажами.", reply_markup=get_back_btn("menu_master"))

    total_pages = math.ceil(len(users) / PAGE_SIZE)
    
    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    current_users = users[start_idx:end_idx]
    
    text = f"👥 <b>Список игроков</b> (Стр. {page + 1}/{total_pages})\n"
    text += "<i>Нажмите на кнопку с ником, чтобы управлять профилем.</i>\n\n"
    
    kb = []

    # --- 1. КНОПКИ НАВИГАЦИИ (Теперь сверху) ---
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"m_users_list:{page - 1}"))
    if page < total_pages - 1:
        nav.append(types.InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"m_users_list:{page + 1}"))
    
    # Добавляем навигацию первой строкой, если она есть
    if nav:
        kb.append(nav)
    # -------------------------------------------
    
    # --- 2. СПИСОК ПОЛЬЗОВАТЕЛЕЙ ---
    for u in current_users:
        # Данные игрока
        main_char = next((c for c in u.characters if c.is_main), None)
        alts = [c.nickname for c in u.characters if not c.is_main]
        
        main_nick = main_char.nickname if main_char else "Без основы"
        user_tag = f"@{u.username}" if u.username else f"ID {u.telegram_id}"
        alts_str = ", ".join(alts) if alts else "нет"
        
        # Текст
        text += f"🔹 <b>{main_nick}</b> ({user_tag})\n"
        text += f"   ╚ <i>Твины: {alts_str}</i>\n\n"
        
        # Кнопка
        btn_text = f"{main_nick} ({user_tag})"
        kb.append([types.InlineKeyboardButton(text=btn_text, callback_data=f"m_u_manage_{u.id}_{page}")]) 

    # --- 3. КНОПКА ВЫХОДА (Снизу) ---
    kb.append([types.InlineKeyboardButton(text="🔙 В меню мастера", callback_data="menu_master")])
    
    await callback.message.edit_text(
        text, 
        parse_mode="HTML", 
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )

@router.callback_query(F.data.startswith("m_u_manage_"))
async def m_user_manage(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    uid, page = int(parts[3]), int(parts[4])
    user = session.get(User, uid)
    if not user: return await callback.answer("Пользователь не найден.", show_alert=True)
    
    chars = session.query(Character).filter_by(user_id=user.id).all()
    user_link = f"<a href='tg://user?id={user.telegram_id}'>{user.username or 'Без юзернейма'}</a>"
    status_emoji = "⛔ ЗАБАНЕН" if user.is_banned else "✅ Активен"
    ban_text = "🕊 Разбанить" if user.is_banned else "🔨 ЗАБАНИТЬ"
    
    text = f"👤 <b>Управление профилем:</b>\nИгрок: {user_link}\nСтатус: <b>{status_emoji}</b>\n\n👇 <b>Список персонажей:</b>"
    kb = [[types.InlineKeyboardButton(text=ban_text, callback_data=f"m_ban_toggle_{uid}_{page}")]]
    for c in chars:
        kb.append([types.InlineKeyboardButton(text=f"❌ {'👑' if c.is_main else '👤'} {c.nickname}", callback_data=f"m_del_char_{c.id}_{uid}_{page}")])
    kb.append([types.InlineKeyboardButton(text="🔙 К списку", callback_data=f"m_users_list:{page}")])
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("m_ban_toggle_"))
async def m_toggle_ban(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    uid, page = int(parts[3]), int(parts[4])
    user = session.get(User, uid)
    if user:
        if user.is_master: return await callback.answer("❌ Нельзя забанить Мастера!", show_alert=True)
        user.is_banned = not user.is_banned
        if user.is_banned: session.query(QueueEntry).filter_by(user_id=uid).delete()
        session.commit()
        await callback.answer(f"Пользователь {'забанен' if user.is_banned else 'разбанен'}.")
        callback.data = f"m_u_manage_{uid}_{page}"
        await m_user_manage(callback)

@router.callback_query(F.data.startswith("m_del_char_"))
async def m_delete_char_admin(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    cid, uid, page = int(parts[3]), int(parts[4]), int(parts[5])
    char = session.get(Character, cid)
    if char:
        nick = char.nickname
        session.delete(char)
        session.query(QueueEntry).filter_by(character_name=nick).delete()
        session.commit()
        await callback.answer(f"✅ Ник {nick} отвязан.")
    else: await callback.answer("Уже удален.")
    
    callback.data = f"m_u_manage_{uid}_{page}"
    await m_user_manage(callback)

# --- ДОБАВЛЕНИЕ АДМИНА ---
@router.callback_query(F.data == "m_add_admin_start")
async def m_add_admin_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("👑 Введи **Telegram Username** игрока (без @):", parse_mode="Markdown", reply_markup=get_back_btn("menu_master"))
    await state.set_state(MasterManageStates.waiting_for_admin_username)

@router.message(MasterManageStates.waiting_for_admin_username)
async def m_add_admin_save(message: types.Message, state: FSMContext):
    target = message.text.replace("@", "").strip()
    user = session.query(User).filter(User.username == target).first()
    if not user: return await message.answer(f"❌ Пользователь @{target} не найден в базе.", reply_markup=get_back_btn("menu_master"))
    
    user.is_master = True
    session.commit()
    await message.answer(f"✅ @{target} теперь Мастер.", reply_markup=get_master_menu())
    await state.clear()

# --- РАЗДАЧА НАГРАД ---
@router.callback_query(F.data == "m_distribute")
async def m_dist_start(callback: types.CallbackQuery):
    queues = session.query(QueueType).all()
    kb = []
    for q in queues:
        count = session.query(QueueEntry).filter_by(queue_type_id=q.id).count()
        kb.append([types.InlineKeyboardButton(text=f"{q.name} ({count})", callback_data=f"dist_{q.id}")])
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text("🎁 <b>Выберите очередь:</b>", parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("dist_"))
async def m_show_dist_list(callback: types.CallbackQuery):
    qid = int(callback.data.split("_")[1])
    q = session.get(QueueType, qid)
    entries = session.query(QueueEntry).filter_by(queue_type_id=qid).all()
    
    if not entries: return await callback.message.edit_text(f"✅ Очередь <b>{q.name}</b> пуста.", parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 Назад", callback_data="m_distribute")]]))
    
    nick_list = "\n".join([e.character_name for e in entries])
    text = f"🎁 <b>Раздача: {q.name}</b>\nСписок:\n<code>{nick_list}</code>\n\n👇 Нажми на ник, после того, как выдашь награду в игре. Я отправлю игроку уведомление:"
    kb = [[types.InlineKeyboardButton(text=f"💰 {e.character_name}", callback_data=f"issue_{e.id}")] for e in entries]
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="m_distribute")])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("issue_"))
async def m_issue_reward(callback: types.CallbackQuery):
    try: eid = int(callback.data.split("_")[1])
    except: return
    entry = session.get(QueueEntry, eid)
    if not entry: return await callback.answer("Уже выдано/удалено.")
    
    qid, q_name, char_nick = entry.queue_type_id, entry.queue.name, entry.character_name
    user = session.get(User, entry.user_id)
    master = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
    
    # Логика поиска основы
    main_nick = char_nick
    if user:
        main_char = session.query(Character).filter_by(user_id=user.id, is_main=True).first()
        if main_char: main_nick = main_char.nickname
    
    # 1. История
    session.add(RewardHistory(user_id=entry.user_id, character_name=char_nick, queue_name=q_name, issued_by=master.username))
    # 2. Гугл таблица
    asyncio.create_task(log_reward_to_sheet(q_name, main_nick, char_nick, master.username))
    # 3. Уведомление
    if user:
        try:
            kb_notify = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔄 Записаться в эту же очередь", callback_data=f"pre_join_{qid}")], [types.InlineKeyboardButton(text="📋 Выбрать новую очередь", callback_data="menu_join")]])
            await bot.send_message(user.telegram_id, f"🎉 <b>Мастер выдал тебе награду:</b> {q_name} ({char_nick})\nЗабери из Клан листа до Вс 23:30 и снова запишись в эту или другую очередь:", parse_mode="HTML", reply_markup=kb_notify)
        except: pass
    
    session.delete(entry)
    session.commit()
    await callback.answer(f"✅ Выдано: {char_nick}")
    
    callback.data = f"dist_{qid}"
    await m_show_dist_list(callback)

# --- ЛИМИТЫ, ОПИСАНИЕ, LOCKS ---
@router.callback_query(F.data == "m_limits_menu")
async def m_limits_menu(callback: types.CallbackQuery):
    g_limit = session.query(Settings).filter_by(key="default_limit").first().value
    kb = [
        [types.InlineKeyboardButton(text=f"🌐 Изм. общий ({g_limit})", callback_data="m_set_global")],
        [types.InlineKeyboardButton(text="👤 Изм. личный", callback_data="m_set_personal")],
        [types.InlineKeyboardButton(text="📋 Список индив. лимитов", callback_data="m_list_limits")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")]
    ]
    await callback.message.edit_text("⚙️ <b>Настройки лимитов</b>", parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "m_list_limits")
async def m_list_personal_limits(callback: types.CallbackQuery):
    users = session.query(User).filter(User.personal_limit != None).all()
    text = "📋 <b>Особые лимиты:</b>\n\n" + ("Нет." if not users else "")
    for u in users:
        mc = session.query(Character).filter_by(user_id=u.id, is_main=True).first()
        name = mc.nickname if mc else u.username
        text += f"👤 <b>{name}</b>: {u.personal_limit}\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_btn("m_limits_menu"))

@router.callback_query(F.data == "m_set_global")
async def m_set_global_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🌐 Введи число для <b>ОБЩЕГО</b> лимита:", parse_mode="HTML", reply_markup=get_back_btn("m_limits_menu"))
    await state.set_state(LimitStates.waiting_for_global_limit)

@router.message(LimitStates.waiting_for_global_limit)
async def m_set_global_save(message: types.Message, state: FSMContext):
    try:
        val = int(message.text)
        if val < 1: raise ValueError
        setting = session.query(Settings).filter_by(key="default_limit").first()
        setting.value = str(val)
        session.commit()
        await message.answer(f"✅ Общий лимит: {val}", reply_markup=get_master_menu())
        await state.clear()
    except: await message.answer("❌ Введи число > 0.")

@router.callback_query(F.data == "m_set_personal")
async def m_set_personal_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("👤 Введи <b>никнейм</b> игрока:", parse_mode="HTML", reply_markup=get_back_btn("m_limits_menu"))
    await state.set_state(LimitStates.waiting_for_nick_limit)

@router.message(LimitStates.waiting_for_nick_limit)
async def m_set_personal_nick(message: types.Message, state: FSMContext):
    char = session.query(Character).filter_by(nickname=message.text.strip()).first()
    if not char: return await message.answer("❌ Не найден.", reply_markup=get_back_btn("m_limits_menu"))
    await state.update_data(user_id=char.user_id, nick=char.nickname)
    await message.answer("Введи лимит (0 = сброс):", reply_markup=get_back_btn("m_limits_menu"))
    await state.set_state(LimitStates.waiting_for_personal_limit_value)

@router.message(LimitStates.waiting_for_personal_limit_value)
async def m_set_personal_save(message: types.Message, state: FSMContext):
    try:
        val = int(message.text)
        data = await state.get_data()
        user = session.get(User, data['user_id'])
        user.personal_limit = val if val > 0 else None
        session.commit()
        await message.answer(f"✅ Лимит для {data['nick']} {'обновлен' if val>0 else 'сброшен'}.", reply_markup=get_master_menu())
        await state.clear()
    except: await message.answer("❌ Число.")

@router.callback_query(F.data == "m_lock_menu")
async def m_lock_menu(callback: types.CallbackQuery):
    queues = session.query(QueueType).filter_by(is_active=True).all()
    kb = []
    for q in queues:
        icon = "🔴 ЗАКРЫТО" if q.is_locked else "🟢 ОТКРЫТО"
        kb.append([types.InlineKeyboardButton(text=f"{icon} {q.name}", callback_data=f"toggle_lock_{q.id}")])
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text("🔒 <b>Управление доступом:</b>", parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("toggle_lock_"))
async def m_toggle_lock(callback: types.CallbackQuery):
    qid = int(callback.data.split("_")[2])
    q = session.get(QueueType, qid)
    q.is_locked = not q.is_locked
    session.commit()
    await callback.answer(f"{q.name}: {'Закрыто' if q.is_locked else 'Открыто'}")
    await m_lock_menu(callback)

@router.callback_query(F.data == "m_edit_desc")
async def m_edit_desc(callback: types.CallbackQuery):
    queues = session.query(QueueType).all()
    kb = [[types.InlineKeyboardButton(text=q.name, callback_data=f"edit_d_{q.id}")] for q in queues]
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text("✏️ Выбери очередь:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("edit_d_"))
async def m_edit_input(callback: types.CallbackQuery, state: FSMContext):
    qid = int(callback.data.split("_")[2])
    q = session.get(QueueType, qid)
    await state.update_data(qid=qid)
    await callback.message.edit_text(f"Текущее: {q.description}\n👇 **Новое описание:**", parse_mode="Markdown", reply_markup=get_back_btn("menu_master"))
    await state.set_state(EditQueueStates.waiting_for_new_description)

@router.message(EditQueueStates.waiting_for_new_description)
async def m_edit_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    q = session.get(QueueType, data['qid'])
    q.description = message.text
    session.commit()
    await message.answer("✅ Сохранено.", reply_markup=get_master_menu())
    await state.clear()

# --- FORCE ADD/DEL & LOGS ---
@router.callback_query(F.data == "m_force_add")
async def m_force_add(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("➕ Никнейм:", reply_markup=get_back_btn("menu_master"))
    await state.set_state(MasterManageStates.waiting_for_nickname_add)

@router.message(MasterManageStates.waiting_for_nickname_add)
async def m_force_nick(message: types.Message, state: FSMContext):
    if not await check_google_sheet(message.text): return await message.answer("❌ Невалидный ник.")
    await state.update_data(nick=message.text)
    kb = [[types.InlineKeyboardButton(text=q.name, callback_data=f"f_add_{q.id}")] for q in session.query(QueueType).all()]
    await message.answer("Куда?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(MasterManageStates.waiting_for_queue_add)

@router.callback_query(F.data.startswith("f_add_"))
async def m_force_add_final(callback: types.CallbackQuery, state: FSMContext):
    qid = int(callback.data.split("_")[2])
    data = await state.get_data()
    nick = data['nick']
    
    char = session.query(Character).filter_by(nickname=nick).first()
    if char: uid, main_nick = char.user_id, session.query(Character).filter_by(user_id=char.user_id, is_main=True).first().nickname
    else: 
        master = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        uid, main_nick = master.id, nick

    session.add(QueueEntry(user_id=uid, queue_type_id=qid, character_name=nick))
    session.commit()
    q_name = session.get(QueueType, qid).name
    asyncio.create_task(log_reward_to_sheet(q_name, main_nick, nick, callback.from_user.username, "👑 Мастер добавил"))
    await callback.message.edit_text(f"✅ {nick} добавлен.", reply_markup=get_master_menu())
    await state.clear()

@router.callback_query(F.data == "m_force_del")
async def m_force_del(callback: types.CallbackQuery):
    queues = session.query(QueueType).all()
    kb = []
    for q in queues:
        if session.query(QueueEntry).filter_by(queue_type_id=q.id).count() > 0:
            kb.append([types.InlineKeyboardButton(text=f"{q.name}", callback_data=f"sel_del_{q.id}")])
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text("❌ Выбери очередь:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("sel_del_"))
async def m_force_del_list(callback: types.CallbackQuery):
    qid = int(callback.data.split("_")[2])
    entries = session.query(QueueEntry).filter_by(queue_type_id=qid).all()
    kb = [[types.InlineKeyboardButton(text=f"❌ {e.character_name}", callback_data=f"kill_{e.id}")] for e in entries]
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text("Кого удалить?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("kill_"))
async def m_kill(callback: types.CallbackQuery):
    eid = int(callback.data.split("_")[1])
    e = session.get(QueueEntry, eid)
    if e:
        qid = e.queue_type_id
        asyncio.create_task(log_reward_to_sheet(e.queue.name, e.character_name, e.character_name, callback.from_user.username, "⛔ Кик Мастером"))
        session.delete(e)
        session.commit()
        await callback.answer("✅ Удалено.")
        callback.data = f"sel_del_{qid}"
        await m_force_del_list(callback)
    else: await callback.answer("Уже удален.")

@router.callback_query(F.data == "m_global_log")
async def m_global_log(callback: types.CallbackQuery):
    hist = session.query(RewardHistory).order_by(RewardHistory.timestamp.desc()).limit(15).all()
    text = "🗄 <b>Лог последних выдач:</b>\n\n" + ("Архив пуст." if not hist else "")
    for h in hist: text += f"• <code>{h.timestamp.strftime('%d.%m')}</code> <b>{h.character_name}</b> → {h.queue_name}\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_btn("menu_master"))

# --- ОБЪЯВЛЕНИЯ (BROADCAST) ---
# Вспомогательные функции для шедулера
async def run_broadcast(ann_id, bot_instance):
    with session.no_autoflush:
        ann = session.get(ScheduledAnnouncement, ann_id)
        if not ann or not ann.is_active: return
        users = session.query(User).all()
        for u in users:
            try: await bot_instance.send_message(u.telegram_id, f"📢 <b>ОБЪЯВЛЕНИЕ</b>\n\n{ann.text}", parse_mode="HTML")
            except: pass
        if ann.schedule_type == 'once_future':
            ann.is_active = False
            session.commit()

def schedule_job(ann, bot_instance):
    job_id = f"ann_{ann.id}"
    try:
        if ann.schedule_type == 'daily':
            h, m = map(int, ann.run_time.split(':'))
            scheduler.add_job(run_broadcast, 'cron', hour=h, minute=m, id=job_id, replace_existing=True, args=[ann.id, bot_instance])
        elif ann.schedule_type == 'weekly':
            h, m = map(int, ann.run_time.split(':'))
            scheduler.add_job(run_broadcast, 'cron', day_of_week=ann.days_of_week, hour=h, minute=m, id=job_id, replace_existing=True, args=[ann.id, bot_instance])
        elif ann.schedule_type == 'once_future':
            dt = datetime.strptime(ann.run_time, "%d.%m.%Y %H:%M")
            dt_msk = MSK.localize(dt)
            scheduler.add_job(run_broadcast, 'date', run_date=dt_msk, id=job_id, replace_existing=True, args=[ann.id, bot_instance])
    except Exception as e: print(f"❌ Error scheduling {job_id}: {e}")

@router.callback_query(F.data == "m_announce")
async def m_ann_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📢 Текст объявления:", reply_markup=get_back_btn("menu_master"))
    await state.set_state(AnnounceStates.waiting_for_text)

@router.message(AnnounceStates.waiting_for_text)
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

@router.callback_query(F.data.startswith("ann_"))
async def m_ann_type(callback: types.CallbackQuery, state: FSMContext):
    atype = callback.data.split("_")[1]
    if atype == "now":
        data = await state.get_data()
        ann = ScheduledAnnouncement(text=data['text'], schedule_type='once_now', run_time='now', is_active=True)
        session.add(ann); session.commit()
        await run_broadcast(ann.id, callback.bot)
        await callback.message.edit_text("✅ Отправлено.", reply_markup=get_master_menu())
        await state.clear()
    elif atype == "future":
        await callback.message.edit_text("📅 Формат: `ДД.ММ.ГГГГ ЧЧ:ММ`", parse_mode="Markdown", reply_markup=get_back_btn("menu_master"))
        await state.set_state(AnnounceStates.waiting_for_datetime)
    elif atype == "daily":
        await state.update_data(days=[])
        await callback.message.edit_text("⏰ Формат: `ЧЧ:ММ`", parse_mode="Markdown", reply_markup=get_back_btn("menu_master"))
        await state.set_state(AnnounceStates.waiting_for_time_only)
    elif atype == "weekly":
        await state.update_data(days=[])
        await callback.message.edit_text("📆 Дни недели:", reply_markup=get_weekdays_kb([]))
        await state.set_state(AnnounceStates.waiting_for_days)

@router.message(AnnounceStates.waiting_for_datetime)
async def process_future_datetime(message: types.Message, state: FSMContext):
    try:
        dt = message.text.strip()
        datetime.strptime(dt, "%d.%m.%Y %H:%M")
        data = await state.get_data()
        ann = ScheduledAnnouncement(text=data['text'], schedule_type='once_future', run_time=dt, is_active=True)
        session.add(ann); session.commit()
        schedule_job(ann, message.bot)
        await message.answer(f"✅ Запланировано на {dt}", reply_markup=get_master_menu())
        await state.clear()
    except: await message.answer("❌ Формат: ДД.ММ.ГГГГ ЧЧ:ММ")

@router.callback_query(F.data.startswith("toggle_day_"))
async def toggle_day(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split("_")[2]
    data = await state.get_data()
    days = data.get('days', [])
    if code in days: days.remove(code)
    else: days.append(code)
    await state.update_data(days=days)
    await callback.message.edit_reply_markup(reply_markup=get_weekdays_kb(days))

@router.callback_query(F.data == "days_confirm")
async def confirm_days(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('days', []): return await callback.answer("Выберите дни!", show_alert=True)
    await callback.message.edit_text("⏰ Формат: `ЧЧ:ММ`", parse_mode="Markdown", reply_markup=get_back_btn("menu_master"))
    await state.set_state(AnnounceStates.waiting_for_time_only)

@router.message(AnnounceStates.waiting_for_time_only)
async def process_time_only(message: types.Message, state: FSMContext):
    try:
        t_str = message.text.strip()
        datetime.strptime(t_str, "%H:%M")
        data = await state.get_data()
        days_list = data.get('days', [])
        sch_type, days_str = ('weekly', ",".join(days_list)) if days_list else ('daily', None)
        ann = ScheduledAnnouncement(text=data['text'], schedule_type=sch_type, run_time=t_str, days_of_week=days_str, is_active=True)
        session.add(ann); session.commit()
        schedule_job(ann, message.bot)
        await message.answer(f"✅ Расписание создано: {t_str}", reply_markup=get_master_menu())
        await state.clear()
    except: await message.answer("❌ Формат: ЧЧ:ММ")

@router.callback_query(F.data == "m_schedule")
async def m_show_schedule(callback: types.CallbackQuery):
    tasks = session.query(ScheduledAnnouncement).filter_by(is_active=True).all()
    text = "🗓 <b>Активные задачи:</b>\n\n" + ("Пусто" if not tasks else "")
    kb = []
    for t in tasks:
        desc = f"⏰ Ежедневно" if t.schedule_type == 'daily' else (f"📆 {t.days_of_week}" if t.schedule_type == 'weekly' else f"📅 {t.run_time}")
        text += f"{desc} в {t.run_time} — {t.text[:10]}...\n"
        kb.append([types.InlineKeyboardButton(text=f"❌ Удалить ({desc})", callback_data=f"del_sch_{t.id}")])
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("del_sch_"))
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