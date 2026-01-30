import math
import asyncio
from datetime import datetime
from aiogram import Router, F, types
from aiogram.types import ChatMemberUpdated
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from apscheduler.jobstores.base import JobLookupError

# Импорты из других файлов проекта
from loader import bot, scheduler, MSK
from database import session, User, Character, QueueEntry, QueueType, RewardHistory, ScheduledAnnouncement, Settings, set_setting, get_setting, Event, Player, get_msk_now, AFKHistory
from keyboards import get_master_menu, get_master_queues_menu, get_master_community_menu, get_master_announce_menu, get_master_system_menu, get_back_btn, get_weekdays_kb
from states import MasterManageStates, EditQueueStates, AnnounceStates, LimitStates
from utils import check_google_sheet, log_reward_to_sheet
from helpers import get_menu_text
from keyboards import get_main_menu # Explicitly ensuring it's available

from aiogram.types import FSInputFile

router = Router()
PAGE_SIZE = 10

# Проверка на мастера
def is_master(telegram_id):
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    return user and user.is_master

def get_weekly_valor_map(nicknames):
    """
    Calculates weekly valor (from Monday) for a list of nicknames.
    Returns: {nickname: total_valor}
    """
    if not nicknames: return {}
    
    from datetime import timedelta
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    start_date = monday.strftime('%Y-%m-%d')
    
    # We need to find role_ids for these nicknames first (from Players table)
    # This assumes nicknames in QueueEntry match Players table exactly (case sensitive-ish)
    
    players = session.query(Player).filter(Player.nickname.in_(nicknames)).all()
    if not players: return {}
    
    role_map = {p.role_id: p.nickname for p in players}
    role_ids = list(role_map.keys())
    
    # Query Events (Type 1 = Valor)
    # Using substr for date comparison as Event.event_date is String "YYYY-MM-DD HH:MM:SS"
    from sqlalchemy import func
    
    events = session.query(Event.role_id, func.sum(Event.value)).filter(
        Event.event_type == 1,
        Event.role_id.in_(role_ids),
        func.substr(Event.event_date, 1, 10) >= start_date
    ).group_by(Event.role_id).all()
    
    result = {}
    
    # Fill with 0 for found players
    for nick in nicknames:
        result[nick] = -1 # Mark as not found initially
        
    for p in players:
        result[p.nickname] = 0
        
    for rid, total in events:
        if rid in role_map:
            nick = role_map[rid]
            result[nick] = total or 0
            
    return result

# --- ПАНЕЛЬ МАСТЕРА ---
@router.callback_query(F.data == "menu_master")
async def master_menu(callback: types.CallbackQuery):
    if not is_master(callback.from_user.id): return
    await callback.message.edit_text("👑 **Панель Мастера**", reply_markup=get_master_menu(), parse_mode="Markdown")

@router.callback_query(F.data == "m_menu_queues")
async def open_queues_menu(callback: types.CallbackQuery):
    if not is_master(callback.from_user.id): return
    await callback.message.edit_text("🛡 **Управление очередями**", reply_markup=get_master_queues_menu(), parse_mode="Markdown")

@router.callback_query(F.data == "m_menu_community")
async def open_community_menu(callback: types.CallbackQuery):
    if not is_master(callback.from_user.id): return
    await callback.message.edit_text("👥 **Сообщество и игроки**", reply_markup=get_master_community_menu(), parse_mode="Markdown")

@router.callback_query(F.data == "m_menu_announce")
async def open_announce_menu(callback: types.CallbackQuery):
    if not is_master(callback.from_user.id): return
    await callback.message.edit_text("📢 **Объявления**", reply_markup=get_master_announce_menu(), parse_mode="Markdown")

@router.callback_query(F.data == "m_menu_system")
async def open_system_menu(callback: types.CallbackQuery):
    if not is_master(callback.from_user.id): return
    await callback.message.edit_text("💾 **Система и Бэкапы**", reply_markup=get_master_system_menu(), parse_mode="Markdown")

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
    await render_user_manage(callback, uid, page)

async def render_user_manage(event, uid, page):
    # Support both CallbackQuery and Message (if needed, though mostly callback here)
    message = event.message if isinstance(event, types.CallbackQuery) else event
    
    user = session.get(User, uid)
    if not user: 
        if isinstance(event, types.CallbackQuery): await event.answer("Пользователь не найден.", show_alert=True)
        return
    
    chars = session.query(Character).filter_by(user_id=user.id).all()
    user_link = f"<a href='tg://user?id={user.telegram_id}'>{user.username or 'Без юзернейма'}</a>"
    status_emoji = "⛔ ЗАБАНЕН" if user.is_banned else "✅ Активен"
    ban_text = "🕊 Разбанить" if user.is_banned else "🔨 ЗАБАНИТЬ"
    
    afk_info = ""
    if user.afk_start and user.afk_end:
        afk_info = f"\n🛌 <b>Текущий AFK:</b> {user.afk_start.strftime('%d.%m')} - {user.afk_end.strftime('%d.%m')}"
    
    # History text
    history_recs = session.query(AFKHistory).filter_by(user_id=user.id).order_by(AFKHistory.start_date.desc()).limit(5).all()
    if history_recs:
        afk_info += "\n\n📜 <b>История AFK:</b>"
        for h in history_recs:
            afk_info += f"\n• {h.start_date.strftime('%d.%m')} - {h.end_date.strftime('%d.%m')}"
    
    text = f"👤 <b>Управление профилем:</b>\nИгрок: {user_link}\nСтатус: <b>{status_emoji}</b>{afk_info}\n\n👇 <b>Выберите персонажа:</b>"
    
    # Buttons
    kb = []
    
    # 1. Ban/Unban
    kb.append([types.InlineKeyboardButton(text=ban_text, callback_data=f"m_ban_toggle_{uid}_{page}")])
    
    # 2. Master Toggle (New)
    if user.is_master:
        kb.append([types.InlineKeyboardButton(text="⚡ Разжаловать из Мастеров", callback_data=f"m_master_toggle_{uid}_{page}")])
    else:
        kb.append([types.InlineKeyboardButton(text="👑 Сделать Мастером", callback_data=f"m_master_toggle_{uid}_{page}")])

    # 3. AFK Set (New)
    kb.append([types.InlineKeyboardButton(text="💤 Установить AFK", callback_data=f"m_afk_set_{uid}_{page}")])

    # 4. Characters
    for c in chars:
        kb.append([types.InlineKeyboardButton(text=f"{'👑' if c.is_main else '👤'} {c.nickname}", callback_data=f"m_char_menu_{c.id}_{uid}_{page}")])
    
    kb.append([types.InlineKeyboardButton(text="🔙 К списку", callback_data=f"m_users_list:{page}")])
    
    await message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("m_master_toggle_"))
async def m_master_toggle_handler(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    uid, page = int(parts[3]), int(parts[4])
    
    user = session.get(User, uid)
    if not user: return await callback.answer("Пользователь не найден.", show_alert=True)
    
    # Self-protection
    if user.telegram_id == callback.from_user.id:
         return await callback.answer("❌ Нельзя изменить статус самому себе!", show_alert=True)

    user.is_master = not user.is_master
    session.commit()
    
    status = "👑 ТЕПЕРЬ МАСТЕР" if user.is_master else "⚡ БОЛЬШЕ НЕ МАСТЕР"
    await callback.answer(f"Статус изменен: {status}")
    
    # Refresh view
    await render_user_manage(callback, uid, page)

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
        await render_user_manage(callback, uid, page)

@router.callback_query(F.data.startswith("m_char_menu_"))
async def m_char_menu(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    cid, uid, page = int(parts[3]), int(parts[4]), int(parts[5])
    char = session.get(Character, cid)
    if not char: return await callback.answer("Персонаж не найден.", show_alert=True)
    
    text = f"⚙️ <b>Управление персонажем:</b>\nНик: <b>{char.nickname}</b>\nРоль: {'👑 Основа' if char.is_main else '👤 Твин'}"
    kb = [
        [types.InlineKeyboardButton(text="✏️ Изменить ник", callback_data=f"m_ren_start_{cid}_{uid}_{page}")],
        [types.InlineKeyboardButton(text="❌ Отвязать/Удалить", callback_data=f"m_del_char_{cid}_{uid}_{page}")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data=f"m_u_manage_{uid}_{page}")]
    ]
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("m_ren_start_"))
async def m_rename_start(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    cid, uid, page = int(parts[3]), int(parts[4]), int(parts[5])
    char = session.get(Character, cid)
    if not char: return await callback.answer("Ошибка char.", show_alert=True)
    
    await callback.message.edit_text(f"✏️ Введите новый никнейм для <b>{char.nickname}</b>:", parse_mode="HTML", reply_markup=get_back_btn(f"m_char_menu_{cid}_{uid}_{page}"))
    await state.update_data(target_cid=cid, uid=uid, page=page)
    await state.set_state(MasterManageStates.waiting_for_rename)

@router.message(MasterManageStates.waiting_for_rename)
async def m_rename_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid, uid, page = data['target_cid'], data['uid'], data['page']
    new_nick = message.text.strip()
    
    char = session.get(Character, cid)
    if not char: 
        await message.answer("Персонаж удален.")
        await state.clear()
        return

    old_nick = char.nickname
    char.nickname = new_nick
    
    # Update Queues
    count = 0
    entries = session.query(QueueEntry).filter_by(character_name=old_nick).all()
    for e in entries:
        e.character_name = new_nick
        count += 1
    
    session.commit()
    
    await message.answer(f"✅ Переименовано: {old_nick} -> {new_nick}\nОбновлено записей в очередях: {count}")
    
    # Return to menu requires building callback object or sending new message with KB.
    # Simpler: just clear state and send text with button.
    # Or mimic callback logic.
    kb = [[types.InlineKeyboardButton(text="🔙 К меню персонажа", callback_data=f"m_char_menu_{cid}_{uid}_{page}")]]
    await message.answer("Готово.", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    await state.clear()

@router.callback_query(F.data.startswith("m_del_char_"))
async def m_delete_char_admin(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    cid, uid, page = int(parts[3]), int(parts[4]), int(parts[5])

    char = session.get(Character, cid)
    
    if char:
        nick = char.nickname
        user_id = char.user_id
        user = session.get(User, user_id)
        
        session.delete(char)
        session.query(QueueEntry).filter_by(character_name=nick).delete()
        session.commit()
        await callback.answer(f"✅ Ник {nick} отвязан.")
        
        # Check for kick
        session.expire_all()
        count = session.query(Character).filter_by(user_id=user_id).count()
        chat_id = get_setting('clan_chat_id')
        
        if count == 0 and chat_id:
            try:
                await bot.ban_chat_member(chat_id, user.telegram_id)
                await bot.unban_chat_member(chat_id, user.telegram_id)
                await bot.send_message(user.telegram_id, "⚠️ Вы были исключены из группы клана, так как администратор удалил вашего последнего персонажа.")
                await callback.message.answer(f"👢 Игрок {user.username} был кикнут из чата (0 персонажей).")
            except Exception as e:
                # Ignore "chat owner" error or log silently
                if "chat owner" not in str(e):
                    await callback.message.answer(f"⚠️ Ошибка кика: {e}")
            
    else: await callback.answer("Уже удален.")
    
    await render_user_manage(callback, uid, page)

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
    
    # Check pending notifications
    pending_count = session.query(RewardHistory).filter_by(is_notified=False).count()
    if pending_count > 0:
        kb.append([types.InlineKeyboardButton(text=f"📧 Разослать уведомления ({pending_count})", callback_data="m_send_batch")])

    for q in queues:
        count = session.query(QueueEntry).filter_by(queue_type_id=q.id).count()
        kb.append([types.InlineKeyboardButton(text=f"{q.name} ({count})", callback_data=f"dist_{q.id}")])
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text("🎁 <b>Выберите очередь:</b>", parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("dist_"))
async def m_show_dist_list(callback: types.CallbackQuery):
    qid = int(callback.data.split("_")[1])
    await render_dist_list(callback, qid)

async def render_dist_list(event, qid):
    message = event.message if isinstance(event, types.CallbackQuery) else event
    
    q = session.get(QueueType, qid)
    entries = session.query(QueueEntry)\
        .outerjoin(Player, QueueEntry.character_name == Player.nickname)\
        .filter(QueueEntry.queue_type_id == qid)\
        .filter((Player.in_clan == 1) | (Player.in_clan == None))\
        .all()
    
    if not entries: 
        return await message.edit_text(f"✅ Очередь <b>{q.name}</b> пуста.", parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 Назад", callback_data="m_distribute")]]))
    
    # Fetch Valor Stats
    nicks = [e.character_name for e in entries]
    valor_map = get_weekly_valor_map(nicks)
    
    nick_list = ""
    now = get_msk_now()
    
    kb = []
    
    for e in entries:
        val = valor_map.get(e.character_name, -1)
        val_str = f"{val} добл." if val != -1 else "нет инфы"
            
        # AFK Check
        afk_mark = ""
        u = e.user
        if u and u.afk_start and u.afk_end:
            if u.afk_start <= now <= u.afk_end.replace(hour=23, minute=59, second=59):
                afk_mark = " 🛌 AFK"
        
        auto_mark = " ♾" if e.auto_requeue else ""
        
        # Add to text list
        nick_list += f"• <code>{e.character_name}</code> ({val_str}){afk_mark}{auto_mark}\n"
        
        # Button: simplified
        btn_text = f"💰 {e.character_name}"
        
        # Row with Reward and Warn buttons
        kb.append([
            types.InlineKeyboardButton(text=btn_text, callback_data=f"issue_{e.id}"),
            types.InlineKeyboardButton(text="⚠️", callback_data=f"warn_{e.id}")
        ])

    text = f"🎁 <b>Раздача: {q.name}</b>\nСписок:\n{nick_list}\n\n👇 Нажми на ник (кнопку), после того, как выдашь награду в игре."
        
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="m_distribute")])
    await message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

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
    
    # 1. История (is_notified=False)
    session.add(RewardHistory(user_id=entry.user_id, character_name=char_nick, queue_name=q_name, issued_by=master.username, is_notified=False))
    
    # 2. Гугл таблица
    asyncio.create_task(log_reward_to_sheet(q_name, main_nick, char_nick, master.username))
    
    # 3. Auto-Requeue Logic
    if entry.auto_requeue:
        # Create new entry at the end suitable for re-queue
        # Check limits? Usually auto-requeue bypasses manual signup limits or respects them?
        # User requirement: "automatically requeued to end of same queue".
        # Let's just add it.
        session.add(QueueEntry(user_id=entry.user_id, queue_type_id=qid, character_name=char_nick, auto_requeue=True))
        status_msg = f"✅ Выдано: {char_nick} (Перезаписан)"
    else:
        status_msg = f"✅ Выдано: {char_nick} (Ушел)"

    # 4. Удаляем старую запись
    session.delete(entry)
    session.commit()
    
    await callback.answer(status_msg)
    await render_dist_list(callback, qid)

@router.callback_query(F.data.startswith("warn_"))
async def m_warn_user(callback: types.CallbackQuery):
    try: eid = int(callback.data.split("_")[1])
    except: return
    entry = session.get(QueueEntry, eid)
    if not entry: return await callback.answer("Запись не найдена.", show_alert=True)
    
    user = session.get(User, entry.user_id)
    master = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
    
    if user:
        # Save as delayed warning
        session.add(RewardHistory(
            user_id=entry.user_id, 
            character_name=entry.character_name, 
            queue_name=entry.queue.name, 
            issued_by=master.username, 
            is_notified=False,
            record_type="warning"
        ))
        session.commit()
        await callback.answer("⚠️ Предупреждение отложено (в список рассылки).")
    else:
        await callback.answer("Ошибка пользователя.")

@router.callback_query(F.data == "m_send_batch")
async def m_send_batch_notifications(callback: types.CallbackQuery):
    pending = session.query(RewardHistory).filter_by(is_notified=False).all()
    if not pending: return await callback.answer("Нет уведомлений для отправки.", show_alert=True)
    
    # Group by User ID
    user_map = {}
    for item in pending:
        if item.user_id not in user_map: user_map[item.user_id] = []
        user_map[item.user_id].append(item)
        
    count_users = 0
    for uid, items in user_map.items():
        user = session.get(User, uid)
        if not user: 
             # Mark as processed if user gone? Or keep pending? 
             # Better to mark processed to avoid stuck loop
             for i in items: i.is_notified = True
             continue
        
        rewards = [i for i in items if i.record_type != "warning"]
        warnings = [i for i in items if i.record_type == "warning"]
        
        msg_text = ""
        
        if rewards:
            msg_text += "🎉 <b>Вам выданы награды!</b>\n\n"
            for item in rewards:
                msg_text += f"🔹 <b>{item.queue_name}</b> ({item.character_name})\n"
                item.is_notified = True
            msg_text += "\n⚠️ <i>Заберите награды из Клан листа в ближайшее время, пока не пропали.</i>\n\n"
            
        if warnings:
            if rewards: msg_text += "───────────────\n\n"
            msg_text += "⚠️ <b>Важные уведомления:</b>\n\n"
            for item in warnings:
                msg_text += f"🔸 <b>{item.queue_name}</b> ({item.character_name}):\n<i>Условия очереди не выполнены, награда не выдана.</i>\n\n"
                item.is_notified = True

        msg_text += "👇 <b>Выберите действие:</b>"
        
        kb_notify = types.InlineKeyboardMarkup(inline_keyboard=[[
             types.InlineKeyboardButton(text="📋 Перейти к очередям", callback_data="menu_join"),
             types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")
        ]])
        
        try:
            await bot.send_message(user.telegram_id, msg_text, parse_mode="HTML", reply_markup=kb_notify)
            count_users += 1
        except: pass
        
    session.commit()
    await callback.answer(f"✅ Отправлено {count_users} пользователям.")
    
    # Refresh menu to hide button if empty
    await m_dist_start(callback)

# --- ЛИМИТЫ, ОПИСАНИЕ, LOCKS ---
@router.callback_query(F.data == "m_limits_menu")
async def m_limits_menu(callback: types.CallbackQuery):
    g_limit = session.query(Settings).filter_by(key="default_limit").first().value
    
    # Fetch personal limits
    p_users = session.query(User).filter(User.personal_limit != None).all()
    
    text = f"⚙️ <b>Настройки лимитов</b>\n\n"
    text += f"🌐 <b>Общий лимит:</b> {g_limit} (записей на человека)\n\n"
    
    if p_users:
        text += "👤 <b>Индивидуальные лимиты:</b>\n"
        for u in p_users:
            main_char = next((c for c in u.characters if c.is_main), None)
            name = main_char.nickname if main_char else (u.username or f"ID {u.telegram_id}")
            text += f"• <b>{name}</b>: {u.personal_limit}\n"
    else:
        text += "👤 <i>Индивидуальных лимитов нет.</i>"

    kb = [
        [types.InlineKeyboardButton(text=f"🌐 Изм. общий ({g_limit})", callback_data="m_set_global")],
        [types.InlineKeyboardButton(text="👤 Изм. личный", callback_data="m_set_personal")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")]
    ]
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

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
    # Fetch personal limits for display
    p_users = session.query(User).filter(User.personal_limit != None).all()
    
    text = "👤 <b>Установка личного лимита.</b>\n\n"
    if p_users:
        text += "📋 <b>Текущие лимиты:</b>\n"
        for u in p_users:
            main_char = next((c for c in u.characters if c.is_main), None)
            name = main_char.nickname if main_char else (u.username or f"ID {u.telegram_id}")
            text += f"• <b>{name}</b>: {u.personal_limit}\n"
        text += "\n"
    else:
        text += "<i>Индивидуальных лимитов нет.</i>\n\n"

    text += "✍️ Введи <b>никнейм игрока</b>, чтобы изменить его лимит:"
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_btn("m_limits_menu"))
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
    if char: 
        uid = char.user_id
        main_char = session.query(Character).filter_by(user_id=char.user_id, is_main=True).first()
        main_nick = main_char.nickname if main_char else nick
    else: 
        uid = None
        main_nick = nick

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
    await render_force_del_list(callback, qid)

async def render_force_del_list(event, qid):
    message = event.message if isinstance(event, types.CallbackQuery) else event
    entries = session.query(QueueEntry).filter_by(queue_type_id=qid).all()
    kb = [[types.InlineKeyboardButton(text=f"❌ {e.character_name}", callback_data=f"kill_{e.id}")] for e in entries]
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await message.edit_text("Кого удалить?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

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
        await callback.answer("✅ Удалено.")
        await render_force_del_list(callback, qid)
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

# --- AFK LIST ---
@router.callback_query(F.data == "m_afk_list")
async def m_afk_list(callback: types.CallbackQuery):
    now = get_msk_now()
    # Find active AFKs
    # Ideally logic: end_date >= now or (start <= now <= end) ? 
    # Let's show all valid future/present periods.
    # filter(User.afk_end >= now) basically.
    
    users = session.query(User).filter(User.afk_end >= now).all()
    
    text = "🛌 <b>Список текущих и будущих AFK:</b>\n\n"
    if not users:
        text += "<i>Никого нет.</i>"
    else:
        for u in users:
            start = u.afk_start.strftime("%d.%m") if u.afk_start else "??"
            end = u.afk_end.strftime("%d.%m") if u.afk_end else "??"
            text += f"👤 <b>{u.nickname}</b> ({u.username}): {start} - {end}\n"
            
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_btn("menu_master"))

# --- ADMIN AFK SETTING ---
from keyboards import get_afk_start_kb, get_afk_end_kb
from handlers.user import parse_date_input # Reuse parser
from datetime import timedelta

@router.callback_query(F.data.startswith("m_afk_set_"))
async def m_afk_admin_start(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    uid, page = int(parts[3]), int(parts[4])
    user = session.get(User, uid)
    if not user: return await callback.answer("Ошибка user")
    
    await state.update_data(target_uid=uid, page=page)
    await callback.message.edit_text(
        f"📅 <b>AFK для {user.username}: Дата НАЧАЛА</b>\n\n"
        "Выберите вариант или напишите дату вручную в формате <code>ДД.ММ</code>.",
        parse_mode="HTML", reply_markup=get_afk_start_kb()
    )
    await state.set_state(MasterManageStates.waiting_for_afk_start)

@router.callback_query(MasterManageStates.waiting_for_afk_start, F.data.startswith("afk_date_"))
async def m_afk_admin_date_click(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[2]
    now = get_msk_now()
    if action == "today": dt = now
    elif action == "tomorrow": dt = now + timedelta(days=1)
    
    await state.update_data(start_date=dt)
    await m_afk_admin_ask_end(callback.message, state)

@router.message(MasterManageStates.waiting_for_afk_start)
async def m_afk_admin_date_manual(message: types.Message, state: FSMContext):
    dt = parse_date_input(message.text)
    if not dt: return await message.answer("⚠️ Неверный формат (ДД.ММ)", reply_markup=get_afk_start_kb())
    await state.update_data(start_date=dt)
    await m_afk_admin_ask_end(message, state)

async def m_afk_admin_ask_end(message, state):
    msg = message if isinstance(message, types.Message) else message.message
    func = msg.edit_text if isinstance(message, types.CallbackQuery) else msg.answer
    await func(
        "🏁 <b>Дата ОКОНЧАНИЯ отсутствия:</b>",
        parse_mode="HTML", reply_markup=get_afk_end_kb()
    )
    await state.set_state(MasterManageStates.waiting_for_afk_end)

@router.callback_query(MasterManageStates.waiting_for_afk_end, F.data.startswith("afk_dur_"))
async def m_afk_admin_dur_click(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    start_dt = data.get("start_date")
    action = callback.data.split("_")[2]
    
    if action == "month":
        import calendar
        now = start_dt
        last_day = calendar.monthrange(now.year, now.month)[1]
        end_dt = now.replace(day=last_day)
    else:
        days = int(action)
        end_dt = start_dt + timedelta(days=days)
        
    await m_afk_admin_finish(callback, state, start_dt, end_dt)

@router.message(MasterManageStates.waiting_for_afk_end)
async def m_afk_admin_dur_manual(message: types.Message, state: FSMContext):
    data = await state.get_data()
    start_dt = data.get("start_date")
    end_dt = parse_date_input(message.text)
    
    # Validation logic same as user
    if not end_dt: return await message.answer("⚠️ Неверный формат.", reply_markup=get_afk_end_kb())
    if end_dt < start_dt: return await message.answer("⚠️ Дата окончания раньше начала.", reply_markup=get_afk_end_kb())
    
    # Determine context for reply usually callback, here message
    # We call finish but finish expects callback for edit. We should handle message properly.
    # Let's adapt finish.
    
    uid = data['target_uid']
    page = data['page']
    user = session.get(User, uid)
    
    user.afk_start = start_dt
    user.afk_end = end_dt
    session.add(AFKHistory(user_id=user.id, start_date=start_dt, end_date=end_dt))
    session.commit()
    
    await message.answer(f"✅ AFK установлен для {user.username}.")
    # We need to render user manage again. We need a callback object or fake it.
    # It's cleaner to just show text and clear state, as we can't easily jump back to inline menu from reply message without sending a fresh one.
    kb = [[types.InlineKeyboardButton(text="🔙 К профилю", callback_data=f"m_u_manage_{uid}_{page}")]]
    await message.answer("Вернуться:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    await state.clear()

async def m_afk_admin_finish(callback, state, start_dt, end_dt):
    data = await state.get_data()
    uid = data['target_uid']
    page = data['page']
    user = session.get(User, uid)
    
    user.afk_start = start_dt
    user.afk_end = end_dt
    session.add(AFKHistory(user_id=user.id, start_date=start_dt, end_date=end_dt))
    session.commit()
    
    await callback.answer(f"✅ AFK установлен.")
    await render_user_manage(callback, uid, page)
    await state.clear()
    if not users:
        text += "<i>Никого нет.</i>"
    else:
        for u in users:
            main_char = next((c for c in u.characters if c.is_main), None)
            name = main_char.nickname if main_char else (u.username or f"ID {u.telegram_id}")
            
            # Status icon
            if u.afk_start <= now <= u.afk_end:
                 status = "🔴 Сейчас AFK"
            else:
                 status = "🟡 Скоро"
            
            text += f"• <b>{name}</b>: {u.afk_start.strftime('%d.%m')} - {u.afk_end.strftime('%d.%m')} ({status})\n"
            
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_btn("m_menu_community"))

# --- ОБЪЯВЛЕНИЯ (BROADCAST) ---

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

# --- БЭКАП БД ---
@router.callback_query(F.data == "m_backup")
async def m_send_backup(callback: types.CallbackQuery):
    # Формируем красивое имя файла с датой: backup_2023-10-25_14-30.db
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"backup_{date_str}.db"
    
    # Путь к файлу внутри контейнера (у тебя он лежит в корне /app/guild_bot.db)
    db_path = "guild_bot.db"
    
    try:
        # Создаем объект файла для отправки
        backup_file = FSInputFile(db_path, filename=filename)
        
        await callback.message.answer_document(
            backup_file, 
            caption=f"📦 <b>Резервная копия базы данных</b>\n📅 {date_str}\n\nСохрани этот файл в надежное место!",
            parse_mode="HTML"
        )
        await callback.answer("Файл отправлен.")
    except Exception as e:
        await callback.answer(f"Ошибка при создании бэкапа: {e}", show_alert=True)

# --- APPROVAL SYSTEM (NEW ACCESS) ---
@router.callback_query(F.data.startswith("appr:"))
async def m_process_approval(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    action = parts[1] # ok, edit, no
    user_id = int(parts[2])
    
    # Optional parts
    reg_type = parts[3] if len(parts) > 3 else "" # main_input, alt_input
    
    # Clean up message buttons first
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    
    target_user = session.get(User, user_id)
    if not target_user: return await callback.answer("Пользователь не найден.", show_alert=True)
    
    # 1. Reject
    if action == "no":
        try: await bot.send_message(target_user.telegram_id, "❌ <b>Ваша заявка отклонена Мастером.</b>", parse_mode="HTML")
        except: pass
        
        # Clear pending state
        target_user.pending_request_nick = None
        session.commit()
        
        await callback.message.answer(f"❌ Заявка отклонена ({target_user.username}).")
        await callback.answer()
        return

    # 2. Approve OK (Direct)
    if action == "ok":
        nick = ":".join(parts[4:]) 
        
        # VALIDATION: Check if request was cancelled (main_input only)
        if reg_type == "main_input":
            if target_user.pending_request_nick != nick:
                try: await callback.message.edit_text(f"⚠️ <b>Заявка неактуальна.</b>\nПользователь отменил её или изменил ник.\n(Запрос: {nick}, Текущий: {target_user.pending_request_nick})")
                except: pass
                await callback.answer("Заявка отменена пользователем.", show_alert=True)
                return

        await finalize_approval(callback, target_user, nick, reg_type)
    
    # 3. Approve Edit (Ask for nick)
    if action == "edit":
        # Need to ask Master for nick.
        await callback.message.answer(f"✍️ Введите правильный ник для {target_user.username}:", reply_markup=get_back_btn("menu_master"))
        await state.update_data(target_uid=user_id, reg_type=reg_type)
        await state.set_state(MasterManageStates.waiting_for_approve_edit)

@router.message(MasterManageStates.waiting_for_approve_edit)
async def m_approve_edit_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = data['target_uid']
    reg_type = data['reg_type']
    nick = message.text.strip()
    
    target_user = session.get(User, uid)
    if target_user:
        await finalize_approval(message, target_user, nick, reg_type)
    
    await state.clear()

async def finalize_approval(event, target_user, nick, reg_type):
    # Logic similar to finish_main_input / finish_alt_input
    # But since we are in admin.py and can't easy import from user.py, we replicate core logic.
    
    # 1. Main Char Logic
    if reg_type == "main_input":
        existing_char = session.query(Character).filter_by(user_id=target_user.id, nickname=nick).first()
        old_main = session.query(Character).filter_by(user_id=target_user.id, is_main=True).first()
        
        if not old_main:
            if existing_char:
                existing_char.is_main = True
                msg = f"🆙 Твин <b>{nick}</b> повышен до Основы (Мастером)!"
            else:
                session.add(Character(user_id=target_user.id, nickname=nick, is_main=True))
                msg = f"✅ Основа установлена: <b>{nick}</b> (Одобрено Мастером)"
                
                # Invite Link for First Char
                count = session.query(Character).filter_by(user_id=target_user.id).count()
                if count == 0: # It was 0 before this add
                     chat_id = get_setting('clan_chat_id')
                     if chat_id:
                        try:
                            # We need bot instance. event can be Message or Callback
                            bot_inst = event.bot
                            link = await bot_inst.create_chat_invite_link(chat_id, member_limit=1, name=f"For {target_user.username}")
                            try: await bot_inst.send_message(target_user.telegram_id, f"👋 Заявка одобрена!\nВот твоя ссылка: {link.invite_link}")
                            except: pass
                        except Exception as e: print(f"Invite error approval: {e}")

        else:
             # Logic for changing main is complex (confirmations etc). 
             # Simplify for Master Force Add: Just do it.
             old_main.is_main = False
             if existing_char: existing_char.is_main = True
             else: session.add(Character(user_id=target_user.id, nickname=nick, is_main=True))
             msg = f"✅ Основа сменена на <b>{nick}</b> (Мастером)."
             
             # Queue updates
             entries = session.query(QueueEntry).filter_by(user_id=target_user.id).all()
             for e in entries:
                 if e.character_name != nick:
                     e.character_name = nick
                     # Log update logic omitted for brevity or can copy-paste log call

    # 2. Alt Logic
    elif reg_type == "alt_input":
        if session.query(Character).filter_by(user_id=target_user.id, nickname=nick).first():
            msg = f"⚠️ Твин {nick} уже был у пользователя."
        else:
            session.add(Character(user_id=target_user.id, nickname=nick, is_main=False))
            msg = f"✅ Твин добавлен: <b>{nick}</b> (Одобрено Мастером)"

    # Clear pending state
    target_user.pending_request_nick = None
    session.commit()
    
    # Notify User with Main Menu
    try:
        # Generate the main menu text with the approval message as header
        menu_text = get_menu_text(target_user, custom_title=msg)
        main_menu_kb = get_main_menu(target_user)
        
        await bot.send_message(target_user.telegram_id, menu_text, parse_mode="HTML", reply_markup=main_menu_kb)
    except: pass
    
    # Notify Master
    kb_master_nav = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
        [types.InlineKeyboardButton(text="👑 Панель Мастера", callback_data="menu_master")]
    ])

    if isinstance(event, types.CallbackQuery):
        await event.message.answer(f"✅ Успешно: {target_user.username} -> {nick}", reply_markup=kb_master_nav)
    else:
        await event.answer(f"✅ Успешно: {target_user.username} -> {nick}", reply_markup=kb_master_nav)

    # Notify Other Masters
    approver_id = event.from_user.id
    approver_user = session.query(User).filter_by(telegram_id=approver_id).first()
    approver_name = f"@{approver_user.username}" if (approver_user and approver_user.username) else "Мастер"
    
    other_masters = session.query(User).filter(User.is_master == True, User.telegram_id != approver_id).all()
    for m in other_masters:
        try:
             await event.bot.send_message(m.telegram_id, f"ℹ️ <b>{approver_name} одобрил заявку:</b>\nИгрок: {target_user.username or 'ID '+str(target_user.id)}\nНик: {nick}", parse_mode="HTML")
        except: pass

# --- ГРУППА КЛАНА ---
@router.message(Command("set_clan_group"))
async def cmd_set_clan_group(message: types.Message):
    if not is_master(message.from_user.id): return
    
    # If command argument is present, use it. Else use current chat.
    args = message.text.split()
    if len(args) > 1:
        chat_id = args[1]
    else:
        chat_id = message.chat.id
        
    set_setting("clan_chat_id", chat_id)
    await message.answer(f"✅ ID этой группы ({chat_id}) сохранен как Клановая Группа.\nТеперь бот будет приглашать сюда новичков и кикать тех, кто удалил всех персонажей.")

# --- VERIFICATION CODE SETTINGS ---
@router.callback_query(F.data == "m_verification")
async def m_verification_menu(callback: types.CallbackQuery):
    code = get_setting("verification_code")
    status = f"✅ ВКЛ ({code})" if code else "❌ ВЫКЛ"
    
    text = f"🔐 <b>Код верификации</b>\nТекущий статус: {status}\n\nЕсли включено, бот будет требовать этот код при добавлении любого персонажа (основы или твина)."
    
    kb = [
        [types.InlineKeyboardButton(text="✏️ Задать код", callback_data="m_set_code")],
        [types.InlineKeyboardButton(text="❌ Отключить проверку", callback_data="m_disable_code")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")]
    ]
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "m_set_code")
async def m_set_code_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🔐 Введите новый код верификации (любое слово или число):", reply_markup=get_back_btn("m_verification"))
    await state.set_state(MasterManageStates.waiting_for_code_setting)

@router.message(MasterManageStates.waiting_for_code_setting)
async def m_set_code_save(message: types.Message, state: FSMContext):
    code = message.text.strip()
    set_setting("verification_code", code)
    await message.answer(f"✅ Код верификации установлен: <b>{code}</b>", parse_mode="HTML", reply_markup=get_master_menu())
    await state.clear()

@router.callback_query(F.data == "m_disable_code")
async def m_disable_code(callback: types.CallbackQuery):
    set_setting("verification_code", None) # None удаляет или ставит null (в нашей функции set_setting надо проверить реализацию, обычно она делает update, если None -> удалим?)
    # Проверим реализацию set_setting. Если она просто пишет строку, то None может упасть или записаться как "None".
    # Лучше записать пустую строку или удалить запись. 
    # В database.py:
    # def set_setting(key, value):
    #     s = session.query(Settings).filter_by(key=key).first()
    #     if s: s.value = value
    #     else: session.add(Settings(key=key, value=value))
    #     session.commit()
    # Если value=None, то s.value = None. В базе Column(String).
    
    # Чтобы было надежнее, удалим запись.
    s = session.query(Settings).filter_by(key="verification_code").first()
    if s: 
        session.delete(s)
        session.commit()
        
    await callback.answer("✅ Проверка кодом отключена.")
    await m_verification_menu(callback)


@router.chat_member()
async def on_user_join(event: ChatMemberUpdated):
    # Проверяем, что это вступление (был left/kicked/restricted -> стал member/creator/administrator)
    old = event.old_chat_member.status
    new = event.new_chat_member.status
    
    # Реагируем только на вступление (member)
    if new not in ["member", "administrator", "creator"]: return
    if old in ["member", "administrator", "creator"]: return # Уже был в чате (смена прав)

    chat_id = get_setting('clan_chat_id')
    current_chat_id = str(event.chat.id)
    
    # Проверяем, что это целевая группа
    if not chat_id or str(chat_id) != current_chat_id: return

    user = event.new_chat_member.user
    if user.is_bot: return

    # Проверка по базе
    db_user = session.query(User).filter_by(telegram_id=user.id).first()
    has_chars = False
    
    if db_user:
        count = session.query(Character).filter_by(user_id=db_user.id).count()
        if count > 0: has_chars = True
    
    if not has_chars:
        try:
            await event.bot.ban_chat_member(event.chat.id, user.id)
            await event.bot.unban_chat_member(event.chat.id, user.id)
            await event.bot.send_message(event.chat.id, f"⛔ Пользователь {user.mention_html()} был исключен (нет персонажей в боте).", parse_mode="HTML")
        except Exception as e:
            await event.bot.send_message(event.chat.id, f"⚠️ Не удалось кикнуть нелегала: {e}")
    else:
        # Можно поприветствовать
        pass