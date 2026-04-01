import asyncio
import glob
import math
import os
import sys
from datetime import datetime, timedelta
from sqlalchemy import func, select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import ChatMemberUpdated

from database import (
    AFKHistory,
    Character,
    Event,
    Player,
    QueueEntry,
    QueueType,
    RewardHistory,
    ScheduledAnnouncement,
    Settings,
    User,
    get_msk_now,
    get_setting,
    set_setting,
)
from handlers.user import parse_date_input
from helpers import (
    get_menu_text,
    get_user_main_role_id,
    update_user_menu_button,
)
from keyboards import (
    get_afk_end_kb,
    get_afk_start_kb,
    get_back_btn,
    get_backup_manage_kb,
    get_backup_menu_kb,
    get_backups_list_kb,
    get_main_menu,  # Explicitly ensuring it's available
    get_master_announce_menu,
    get_master_community_menu,
    get_master_menu,
    get_master_queues_menu,
    get_master_system_menu,
    get_restore_confirm_kb,
    get_weekdays_kb,
)

# Импорты из других файлов проекта
from loader import MSK, bot, scheduler
from logic.queue_ops import get_admin_queue_count, get_admin_queue_entries
from logic.reward_ops import issue_reward, warn_user
from scripts.backup_db import perform_backup
from scripts.restore_db import restore as restore_db_func
from states import AnnounceStates, EditQueueStates, LimitStates, MasterManageStates
from utils import check_google_sheet, log_reward_to_sheet

router = Router()
PAGE_SIZE = 10


# Проверка на мастера
async def is_master(session: AsyncSession, telegram_id: int):
    result = await session.execute(select(User).filter_by(telegram_id=telegram_id))
    user = result.scalars().first()
    return user and user.is_master


async def get_weekly_valor_map(session: AsyncSession, nicknames):
    """
    Calculates weekly valor (from Monday) for a list of nicknames.
    Returns: {nickname: total_valor}
    """
    if not nicknames:
        return {}

    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    start_date = monday.strftime("%Y-%m-%d")

    # We need to find role_ids for these nicknames first (from Players table)
    # This assumes nicknames in QueueEntry match Players table exactly (case sensitive-ish)
    result_players = await session.execute(select(Player).filter(Player.nickname.in_(nicknames)))
    players = result_players.scalars().all()
    if not players:
        return {}

    role_map = {p.role_id: p.nickname for p in players}
    role_ids = list(role_map.keys())

    # Query Events (Type 1 = Valor)
    # Using substr for date comparison as Event.event_date is String "YYYY-MM-DD HH:MM:SS"
    stmt = (
        select(Event.role_id, func.sum(Event.value))
        .filter(Event.event_type == 1, Event.role_id.in_(role_ids), func.substr(Event.event_date, 1, 10) >= start_date)
        .group_by(Event.role_id)
    )
    result_events = await session.execute(stmt)
    events = result_events.all()

    result = {}

    # Fill with 0 for found players
    for nick in nicknames:
        result[nick] = -1  # Mark as not found initially

    for p in players:
        result[p.nickname] = 0

    for rid, total in events:
        if rid in role_map:
            nick = role_map[rid]
            result[nick] = total or 0

    return result


# --- ПАНЕЛЬ МАСТЕРА ---
@router.callback_query(F.data == "menu_master")
async def master_menu(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await master_menu(callback, session)
    if not await is_master(session, callback.from_user.id):
        return
    await callback.message.edit_text("👑 **Панель Мастера**", reply_markup=get_master_menu(), parse_mode="Markdown")


@router.callback_query(F.data == "m_menu_queues")
async def open_queues_menu(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await open_queues_menu(callback, session)
    if not await is_master(session, callback.from_user.id):
        return
    await callback.message.edit_text(
        "🛡 **Управление очередями**", reply_markup=get_master_queues_menu(), parse_mode="Markdown"
    )


@router.callback_query(F.data == "m_menu_community")
async def open_community_menu(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await open_community_menu(callback, session)
    if not await is_master(session, callback.from_user.id):
        return
    await callback.message.edit_text(
        "👥 **Сообщество и игроки**", reply_markup=get_master_community_menu(), parse_mode="Markdown"
    )


@router.callback_query(F.data == "m_menu_announce")
async def open_announce_menu(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await open_announce_menu(callback, session)
    if not await is_master(session, callback.from_user.id):
        return
    await callback.message.edit_text(
        "📢 **Объявления**", reply_markup=get_master_announce_menu(), parse_mode="Markdown"
    )


@router.callback_query(F.data == "m_menu_system")
async def open_system_menu(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await open_system_menu(callback, session)
    if not await is_master(session, callback.from_user.id):
        return
    await callback.message.edit_text(
        "💾 **Система и Бэкапы**", reply_markup=get_master_system_menu(), parse_mode="Markdown"
    )

@router.callback_query(F.data == "instruction_upload_db")
async def instruction_upload_db(callback: types.CallbackQuery):
    text = (
        "📖 <b>Инструкция по обновлению сайта</b>\n\n"
        "1. Скачайте и запустите <code>FactionBoard4-29.exe</code> (прикреплен ниже).\n"
        "2. При первом запуске программа может запросить путь к папке FactionHistoryData.\n"
        "Нужно вставить ссылку вида: <code>&lt;папка с игрой&gt;\\Perfect World\\element\\userdata\\FactionHistoryData</code>\n"
        "3. В игре откройте <b>Историю гильдии</b>.\n"
        "4. Проскрольте историю гильдии до конца или до момента, когда на сайте было последнее обновление.\n\n"
        "<i>В момент, когда вы скролите историю, в вашей папке с игрой создаётся и записывается файл с этой историей, который программа отправит на сайт. В файл может записаться только ограниченное количество событий, поэтому, чтобы никакие данные не потерялись, историю гильдии рекомендуется открывать и скроллить <b>4 раза в среду</b> (танцы и адепты генерируют большое количество записей) и <b>2 раза в другой день</b>.</i>\n\n"
        "5. Закройте историю гильдии. Через 3 минуты информация на сайте обновится."
    )
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="instruction_back_from_upload")],
        [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    
    # Check if FactionBoard4-29.exe is in the project root
    import os
    exe_path = os.path.join(os.getcwd(), "FactionBoard4-29.exe")
    if os.path.exists(exe_path):
        from aiogram.types import FSInputFile
        from loader import bot
        
        # Show loading message
        await callback.message.edit_text("⏳ <i>Загружаю инструкцию и файл программы, пожалуйста подождите...</i>", parse_mode="HTML")
        
        doc = FSInputFile(exe_path)
        await bot.send_document(
            chat_id=callback.message.chat.id, 
            document=doc, 
            caption=text, 
            parse_mode="HTML", 
            reply_markup=kb,
            request_timeout=300
        )
        await callback.message.delete()
    else:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data == "instruction_back_from_upload")
async def instruction_back_from_upload(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await instruction_back_from_upload(callback, session)
    # Depending on context, it could just be a generic back, or delete the doc message
    # It's cleaner to handle deletion and resending menu
    await callback.message.delete()
    text = (
            "🔔 <b>Напоминание!</b>\n\n"
            "Пожалуйста, запустите <code>FactionBoard4-29.exe</code> и проскрольте историю гильдии в игре, "
            "чтобы не потерять события.\n\n"
            "<i>Примерное рекомендуемое время для скролинга истории гильдии:\n"
            "Ежедневно: в 12:00 (до вечернего пика) и в 21:30 (после).\n"
            "По средам (дополнительно): в 18:30 и 20:00(чтобы не потерялись танцы и адепты).</i>"
        )

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="📖 Инструкция по обновлению сайта", callback_data="instruction_upload_db")],
            [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")]
    ])
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)

# --- УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ---
@router.callback_query(F.data.startswith("m_users_list"))
async def m_users_list(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_users_list(callback, session)
    try:
        page = int(callback.data.split(":")[1])
    except Exception:
        page = 0

    # Need eager loading or session-bound object for characters
    stmt = select(User).join(Character).options(selectinload(User.characters)).distinct()
    result = await session.execute(stmt)
    users = result.scalars().all()

    if not users:
        return await callback.message.edit_text(
            "🤷‍♂️ В базе пока нет игроков с персонажами.", reply_markup=get_back_btn("menu_master")
        )

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
        text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data.startswith("m_u_manage_"))
async def m_user_manage(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_user_manage(callback, session)
    parts = callback.data.split("_")
    uid, page = int(parts[3]), int(parts[4])
    await render_user_manage(callback, uid, page, session)


async def render_user_manage(event, uid, page, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await render_user_manage(event, uid, page, session)
    # Support both CallbackQuery and Message (if needed, though mostly callback here)
    message = event.message if isinstance(event, types.CallbackQuery) else event

    user = await session.get(User, uid)
    if not user:
        if isinstance(event, types.CallbackQuery):
            await event.answer("Пользователь не найден.", show_alert=True)
        return

    result_chars = await session.execute(select(Character).filter_by(user_id=user.id))
    chars = result_chars.scalars().all()
    user_link = f"<a href='tg://user?id={user.telegram_id}'>{user.username or 'Без юзернейма'}</a>"
    status_emoji = "⛔ ЗАБАНЕН" if user.is_banned else "✅ Активен"
    ban_text = "🕊 Разбанить" if user.is_banned else "🔨 ЗАБАНИТЬ"

    afk_info = ""
    if user.afk_start and user.afk_end:
        afk_info = f"\n🛌 <b>Текущий AFK:</b> {user.afk_start.strftime('%d.%m')} - {user.afk_end.strftime('%d.%m')}"

    # History text
    stmt_afk = select(AFKHistory).filter_by(user_id=user.id).order_by(AFKHistory.start_date.desc()).limit(5)
    result_afk = await session.execute(stmt_afk)
    history_recs = result_afk.scalars().all()
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
        kb.append(
            [
                types.InlineKeyboardButton(
                    text="⚡ Разжаловать из Мастеров", callback_data=f"m_master_toggle_{uid}_{page}"
                )
            ]
        )
    else:
        kb.append(
            [types.InlineKeyboardButton(text="👑 Сделать Мастером", callback_data=f"m_master_toggle_{uid}_{page}")]
        )

    # 3. AFK Set (New)
    kb.append([types.InlineKeyboardButton(text="💤 Установить AFK", callback_data=f"m_afk_set_{uid}_{page}")])

    # 4. Characters
    for c in chars:
        kb.append(
            [
                types.InlineKeyboardButton(
                    text=f"{'👑' if c.is_main else '👤'} {c.nickname}", callback_data=f"m_char_menu_{c.id}_{uid}_{page}"
                )
            ]
        )

    kb.append([types.InlineKeyboardButton(text="🔙 К списку", callback_data=f"m_users_list:{page}")])

    await message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data.startswith("m_master_toggle_"))
async def m_master_toggle_handler(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_master_toggle_handler(callback, session)
    parts = callback.data.split("_")
    uid, page = int(parts[3]), int(parts[4])

    user = await session.get(User, uid)
    if not user:
        return await callback.answer("Пользователь не найден.", show_alert=True)

    # Self-protection
    if user.telegram_id == callback.from_user.id:
        return await callback.answer("❌ Нельзя изменить статус самому себе!", show_alert=True)

    user.is_master = not user.is_master
    await session.commit()

    status = "👑 ТЕПЕРЬ МАСТЕР" if user.is_master else "⚡ БОЛЬШЕ НЕ МАСТЕР"
    await callback.answer(f"Статус изменен: {status}")

    # Refresh view
    await render_user_manage(callback, uid, page, session)


@router.callback_query(F.data.startswith("m_ban_toggle_"))
async def m_toggle_ban(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_toggle_ban(callback, session)
    parts = callback.data.split("_")
    uid, page = int(parts[3]), int(parts[4])
    user = await session.get(User, uid)
    if user:
        if user.is_master:
            return await callback.answer("❌ Нельзя забанить Мастера!", show_alert=True)
        user.is_banned = not user.is_banned
        if user.is_banned:
            from sqlalchemy import delete
            await session.execute(delete(QueueEntry).filter_by(user_id=uid))
        await session.commit()
        await callback.answer(f"Пользователь {'забанен' if user.is_banned else 'разбанен'}.")
        await render_user_manage(callback, uid, page, session)


@router.callback_query(F.data.startswith("m_char_menu_"))
async def m_char_menu(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_char_menu(callback, session)
    parts = callback.data.split("_")
    cid, uid, page = int(parts[3]), int(parts[4]), int(parts[5])
    char = await session.get(Character, cid)
    if not char:
        return await callback.answer("Персонаж не найден.", show_alert=True)

    text = f"⚙️ <b>Управление персонажем:</b>\nНик: <b>{char.nickname}</b>\nРоль: {'👑 Основа' if char.is_main else '👤 Твин'}"
    kb = [
        [types.InlineKeyboardButton(text="✏️ Изменить ник", callback_data=f"m_ren_start_{cid}_{uid}_{page}")],
        [types.InlineKeyboardButton(text="❌ Отвязать/Удалить", callback_data=f"m_del_char_{cid}_{uid}_{page}")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data=f"m_u_manage_{uid}_{page}")],
    ]
    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data.startswith("m_ren_start_"))
async def m_rename_start(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_rename_start(callback, state, session)
    parts = callback.data.split("_")
    cid, uid, page = int(parts[3]), int(parts[4]), int(parts[5])
    char = await session.get(Character, cid)
    if not char:
        return await callback.answer("Ошибка char.", show_alert=True)

    await callback.message.edit_text(
        f"✏️ Введите новый никнейм для <b>{char.nickname}</b>:",
        parse_mode="HTML",
        reply_markup=get_back_btn(f"m_char_menu_{cid}_{uid}_{page}"),
    )
    await state.update_data(target_cid=cid, uid=uid, page=page)
    await state.set_state(MasterManageStates.waiting_for_rename)


@router.message(MasterManageStates.waiting_for_rename)
async def m_rename_save(message: types.Message, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_rename_save(message, state, session)
    data = await state.get_data()
    cid, uid, page = data["target_cid"], data["uid"], data["page"]
    new_nick = message.text.strip()

    char = await session.get(Character, cid)
    if not char:
        await message.answer("Персонаж удален.")
        await state.clear()
        return

    old_nick = char.nickname
    char.nickname = new_nick

    # Sync with Player table for website
    from database import Player
    from sqlalchemy import func
    stmt_p = select(Player).where(func.lower(Player.nickname) == func.lower(old_nick))
    result_p = await session.execute(stmt_p)
    player_obj = result_p.scalars().first()
    if player_obj:
        player_obj.nickname = new_nick
        player_obj.user_id = uid

    # Update Queues
    count = 0
    from sqlalchemy import update
    result_update = await session.execute(
        update(QueueEntry).filter_by(character_name=old_nick).values(character_name=new_nick)
    )
    count = result_update.rowcount

    await session.commit()

    await message.answer(f"✅ Переименовано: {old_nick} -> {new_nick}\nОбновлено записей в очередях: {count}")

    # Return to menu requires building callback object or sending new message with KB.
    # Simpler: just clear state and send text with button.
    # Or mimic callback logic.
    kb = [[types.InlineKeyboardButton(text="🔙 К меню персонажа", callback_data=f"m_char_menu_{cid}_{uid}_{page}")]]
    await message.answer("Готово.", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    await state.clear()


@router.callback_query(F.data.startswith("m_del_char_"))
async def m_delete_char_admin(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_delete_char_admin(callback, session)
    parts = callback.data.split("_")
    cid, uid, page = int(parts[3]), int(parts[4]), int(parts[5])

    char = await session.get(Character, cid)

    if char:
        nick = char.nickname
        user_id = char.user_id

        await session.delete(char)

        # Sync with Player table for website (clear user_id and reset is_alt to false since it's no longer linked)
        from database import Player
        from sqlalchemy import func
        stmt_p = select(Player).where(func.lower(Player.nickname) == func.lower(nick))
        result_p = await session.execute(stmt_p)
        player_obj = result_p.scalars().first()
        if player_obj:
            player_obj.user_id = None
            player_obj.is_alt = False # Default back to False if unlinked? Or keep?
            # User probably wants it unlinked on site too.

        # Delete from all active queues (used to be update/orphan)
        await session.execute(
            delete(QueueEntry).filter_by(character_name=nick)
        )
        await session.commit()
        await callback.answer(f"✅ Ник {nick} отвязан.")

        # Check for kick
        session.expire_all()
    else:
        await callback.answer("Уже удален.")

    await render_user_manage(callback, uid, page, session)


# --- ДОБАВЛЕНИЕ АДМИНА ---
@router.callback_query(F.data == "m_add_admin_start")
async def m_add_admin_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "👑 Введи **Telegram Username** игрока (без @):",
        parse_mode="Markdown",
        reply_markup=get_back_btn("menu_master"),
    )
    await state.set_state(MasterManageStates.waiting_for_admin_username)


@router.message(MasterManageStates.waiting_for_admin_username)
async def m_add_admin_save(message: types.Message, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_add_admin_save(message, state, session)
    target = message.text.replace("@", "").strip()
    result = await session.execute(select(User).filter(User.username == target))
    user = result.scalars().first()
    if not user:
        return await message.answer(
            f"❌ Пользователь @{target} не найден в базе.", reply_markup=get_back_btn("menu_master")
        )

    user.is_master = True
    await session.commit()
    await message.answer(f"✅ @{target} теперь Мастер.", reply_markup=get_master_menu())
    await state.clear()


# --- РАЗДАЧА НАГРАД ---
@router.callback_query(F.data == "m_distribute")
async def m_dist_start(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_dist_start(callback, session)
    session.expire_all()
    stmt_queues = select(QueueType).filter_by(is_active=True)
    result_queues = await session.execute(stmt_queues)
    queues = result_queues.scalars().all()
    kb = []

    # Check pending notifications
    stmt_pending = select(func.count(RewardHistory.id)).filter_by(is_notified=False)
    result_pending = await session.execute(stmt_pending)
    pending_count = result_pending.scalar() or 0
    if pending_count > 0:
        kb.append(
            [
                types.InlineKeyboardButton(
                    text=f"📧 Разослать уведомления ({pending_count})", callback_data="m_send_batch"
                )
            ]
        )

    for q in queues:
        count = await get_admin_queue_count(session, q.id)
        kb.append([types.InlineKeyboardButton(text=f"{q.name} ({count})", callback_data=f"dist_{q.id}")])
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text(
        "🎁 <b>Выберите очередь:</b>", parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data.startswith("dist_"))
async def m_show_dist_list(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_show_dist_list(callback, session)
    qid = int(callback.data.split("_")[1])
    await render_dist_list(callback, qid, session)


async def render_dist_list(event, qid, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await render_dist_list(event, qid, session)
    session.expire_all()
    message = event.message if isinstance(event, types.CallbackQuery) else event

    q = await session.get(QueueType, qid)
    entries = await get_admin_queue_entries(session, qid)

    if not entries:
        return await message.edit_text(
            f"✅ Очередь <b>{q.name}</b> пуста.",
            parse_mode="HTML",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[[types.InlineKeyboardButton(text="🔙 Назад", callback_data="m_distribute")]]
            ),
        )

    # Fetch Valor Stats
    nicks = [e.character_name for e in entries]
    valor_map = await get_weekly_valor_map(session, nicks)

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
        kb.append(
            [
                types.InlineKeyboardButton(text=btn_text, callback_data=f"issue_{e.id}"),
                types.InlineKeyboardButton(text="⚠️", callback_data=f"warn_{e.id}"),
            ]
        )

    text = f"🎁 <b>Раздача: {q.name}</b>\nСписок:\n{nick_list}\n\n👇 Нажми на ник (кнопку), после того, как выдашь награду в игре."

    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="m_distribute")])
    await message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data.startswith("issue_"))
async def m_issue_reward(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_issue_reward(callback, session)
    try:
        eid = int(callback.data.split("_")[1])
    except Exception:
        return
    
    # Use select with selectinload to avoid MissingGreenlet error on entry.queue.name
    stmt = select(QueueEntry).filter_by(id=eid).options(selectinload(QueueEntry.queue))
    result = await session.execute(stmt)
    entry = result.scalars().first()

    if not entry:
        return await callback.answer("Уже выдано/удалено.")

    qid, q_name, char_nick = entry.queue_type_id, entry.queue.name, entry.character_name
    uid = entry.user_id
    
    result_master = await session.execute(select(User).filter_by(telegram_id=callback.from_user.id))
    master = result_master.scalars().first()

    # Логика поиска основы
    main_nick = char_nick
    if uid:
        stmt_main = select(Character).filter_by(user_id=uid, is_main=True)
        result_main = await session.execute(stmt_main)
        main_char = result_main.scalars().first()
        if main_char:
            main_nick = main_char.nickname

    # LOGIC CALL
    success, msg, hist = await issue_reward(session, entry.id, master.username if master else "Admin")

    if success:
        # Side Effects (Google Sheet)
        asyncio.create_task(log_reward_to_sheet(q_name, main_nick, char_nick, master.username if master else "Admin"))

        await callback.answer(msg)
        await render_dist_list(callback, qid, session)
    else:
        await callback.answer(msg, show_alert=True)


@router.callback_query(F.data.startswith("warn_"))
async def m_warn_user(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_warn_user(callback, session)
    try:
        eid = int(callback.data.split("_")[1])
    except Exception:
        return
    
    # Use select with selectinload to avoid potential MissingGreenlet errors
    stmt = select(QueueEntry).filter_by(id=eid).options(selectinload(QueueEntry.queue))
    result = await session.execute(stmt)
    entry = result.scalars().first()

    if not entry:
        return await callback.answer("Запись не найдена.", show_alert=True)

    result_master = await session.execute(select(User).filter_by(telegram_id=callback.from_user.id))
    master = result_master.scalars().first()

    success, msg, hist = await warn_user(session, entry.id, master.username if master else "Admin")

    await callback.answer(msg)


@router.callback_query(F.data == "m_send_batch")
async def m_send_batch_notifications(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_send_batch_notifications(callback, session)
    stmt = select(RewardHistory).filter_by(is_notified=False)
    result = await session.execute(stmt)
    pending = result.scalars().all()
    if not pending:
        return await callback.answer("Нет уведомлений для отправки.", show_alert=True)

    # Group by User ID
    user_map = {}
    for item in pending:
        if item.user_id not in user_map:
            user_map[item.user_id] = []
        user_map[item.user_id].append(item)

    count_users = 0
    for uid, items in user_map.items():
        user = await session.get(User, uid)
        if not user:
            # Mark as processed if user gone? Or keep pending?
            # Better to mark processed to avoid stuck loop
            for i in items:
                i.is_notified = True
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
            if rewards:
                msg_text += "───────────────\n\n"
            msg_text += "⚠️ <b>Важные уведомления:</b>\n\n"
            for item in warnings:
                msg_text += f"🔸 <b>{item.queue_name}</b> ({item.character_name}):\n<i>Условия очереди не выполнены, награда не выдана.</i>\n\n"
                item.is_notified = True
        msg_text += "👇 <b>Выберите действие:</b>"

        kb_notify = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(text="📋 Перейти к очередям", callback_data="menu_join"),
                    types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main"),
                ]
            ]
        )

        try:
            await bot.send_message(user.telegram_id, msg_text, parse_mode="HTML", reply_markup=kb_notify)
            count_users += 1
        except Exception:
            pass

    # --- PUBLIC LOG BROADCAST ---
    log_enabled = await get_setting(session, "public_log_enabled")
    log_channel = await get_setting(session, "public_log_channel_id")

    if log_enabled == "true" and log_channel:
        try:
            queues_map = {}  # {QueueName: [Nick1, Nick2]}

            all_items = []
            for items in user_map.values():
                all_items.extend(items)

            for item in all_items:
                if item.record_type != "warning":
                    if item.queue_name not in queues_map:
                        queues_map[item.queue_name] = []
                    queues_map[item.queue_name].append(item.character_name)

            if queues_map:
                # Build Message
                log_text = "🎉 <b>Награды отправлены! Не забудьте забрать из Клан листа.</b>\n\n"

                for q_name, nicks in queues_map.items():
                    log_text += f"🛡 <b>{q_name}</b>\n"
                    for n in nicks:
                        log_text += f"• {n}\n"
                    log_text += "\n"

                # Send
                thread_id = await get_setting(session, "public_log_thread_id")
                await bot.send_message(log_channel, log_text, parse_mode="HTML", message_thread_id=thread_id)

        except Exception as e:
            print(f"Failed to send public log: {e}")
            # Don't fail the whole flow
    # ----------------------------

    await session.commit()
    await callback.answer(f"✅ Отправлено {count_users} пользователям.")

    # Refresh menu to hide button if empty
    await m_dist_start(callback, session)


# --- ЛИМИТЫ, ОПИСАНИЕ, LOCKS ---
@router.callback_query(F.data == "m_limits_menu")
@router.callback_query(F.data == "m_limits_menu")
async def m_limits_menu(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_limits_menu(callback, session)
    stmt_global = select(Settings).filter_by(key="default_limit")
    result_global = await session.execute(stmt_global)
    g_limit_obj = result_global.scalars().first()
    g_limit = g_limit_obj.value if g_limit_obj else "Unknown"

    # Fetch personal limits
    stmt_personal = select(User).filter(User.personal_limit.is_not(None)).options(selectinload(User.characters))
    result_personal = await session.execute(stmt_personal)
    p_users = result_personal.scalars().all()

    text = "⚙️ <b>Настройки лимитов</b>\n\n"
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
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")],
    ]
    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data == "m_set_global")
async def m_set_global_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🌐 Введи число для <b>ОБЩЕГО</b> лимита:", parse_mode="HTML", reply_markup=get_back_btn("m_limits_menu")
    )
    await state.set_state(LimitStates.waiting_for_global_limit)


@router.message(LimitStates.waiting_for_global_limit)
async def m_set_global_save(message: types.Message, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_set_global_save(message, state, session)
    try:
        val = int(message.text)
        if val < 1:
            raise ValueError
        stmt = select(Settings).filter_by(key="default_limit")
        result = await session.execute(stmt)
        setting = result.scalars().first()
        if setting:
            setting.value = str(val)
        await session.commit()
        await message.answer(f"✅ Общий лимит: {val}", reply_markup=get_master_menu())
        await state.clear()
    except Exception:
        await message.answer("❌ Введи число > 0.")


@router.callback_query(F.data == "m_set_personal")
async def m_set_personal_start(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_set_personal_start(callback, state, session)
    # Fetch personal limits for display
    stmt = select(User).filter(User.personal_limit.is_not(None)).options(selectinload(User.characters))
    result = await session.execute(stmt)
    p_users = result.scalars().all()

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
async def m_set_personal_nick(message: types.Message, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_set_personal_nick(message, state, session)
    stmt = select(Character).filter_by(nickname=message.text.strip())
    result = await session.execute(stmt)
    char = result.scalars().first()
    if not char:
        return await message.answer("❌ Не найден.", reply_markup=get_back_btn("m_limits_menu"))
    await state.update_data(user_id=char.user_id, nick=char.nickname)
    await message.answer("Введи лимит (0 = сброс):", reply_markup=get_back_btn("m_limits_menu"))
    await state.set_state(LimitStates.waiting_for_personal_limit_value)


@router.message(LimitStates.waiting_for_personal_limit_value)
async def m_set_personal_save(message: types.Message, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_set_personal_save(message, state, session)
    try:
        val = int(message.text)
        data = await state.get_data()
        user = await session.get(User, data["user_id"])
        user.personal_limit = val if val > 0 else None
        await session.commit()
        await message.answer(
            f"✅ Лимит для {data['nick']} {'обновлен' if val>0 else 'сброшен'}.", reply_markup=get_master_menu()
        )
        await state.clear()
    except Exception:
        await message.answer("❌ Число.")


@router.callback_query(F.data == "m_lock_menu")
async def m_lock_menu(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_lock_menu(callback, session)
    stmt = select(QueueType).filter_by(is_active=True)
    result = await session.execute(stmt)
    queues = result.scalars().all()
    kb = []
    for q in queues:
        icon = "🔴 ЗАКРЫТО" if q.is_locked else "🟢 ОТКРЫТО"
        kb.append([types.InlineKeyboardButton(text=f"{icon} {q.name}", callback_data=f"toggle_lock_{q.id}")])
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text(
        "🔒 <b>Управление доступом:</b>", parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data.startswith("toggle_lock_"))
async def m_toggle_lock(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_toggle_lock(callback, session)
    qid = int(callback.data.split("_")[2])
    q = await session.get(QueueType, qid)
    q.is_locked = not q.is_locked
    await session.commit()
    await callback.answer(f"{q.name}: {'Закрыто' if q.is_locked else 'Открыто'}")
    await m_lock_menu(callback, session)


@router.callback_query(F.data == "m_edit_desc")
async def m_edit_desc(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_edit_desc(callback, session)
    stmt = select(QueueType).filter_by(is_active=True)
    result = await session.execute(stmt)
    queues = result.scalars().all()
    kb = [[types.InlineKeyboardButton(text=q.name, callback_data=f"edit_d_{q.id}")] for q in queues]
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text("✏️ Выбери очередь:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data.startswith("edit_d_"))
async def m_edit_input(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_edit_input(callback, state, session)
    qid = int(callback.data.split("_")[2])
    q = await session.get(QueueType, qid)
    await state.update_data(qid=qid)
    await callback.message.edit_text(
        f"Текущее: {q.description}\n👇 **Новое описание:**",
        parse_mode="Markdown",
        reply_markup=get_back_btn("menu_master"),
    )
    await state.set_state(EditQueueStates.waiting_for_new_description)


@router.message(EditQueueStates.waiting_for_new_description)
async def m_edit_save(message: types.Message, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_edit_save(message, state, session)
    data = await state.get_data()
    q = await session.get(QueueType, data["qid"])
    q.description = message.text
    await session.commit()
    await message.answer("✅ Сохранено.", reply_markup=get_master_menu())
    await state.clear()


# --- FORCE ADD/DEL & LOGS ---
@router.callback_query(F.data == "m_force_add")
async def m_force_add(callback: types.CallbackQuery, state: FSMContext):
    kb = [
        [types.InlineKeyboardButton(text="➕ Ввести 1 ник", callback_data="m_force_single")],
        [types.InlineKeyboardButton(text="📝 Добавить списком", callback_data="m_force_bulk")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")],
    ]
    await callback.message.edit_text(
        "Выбери режим добавления:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data == "m_force_single")
async def m_force_single_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("➕ Никнейм:", reply_markup=get_back_btn("m_force_add"))
    await state.set_state(MasterManageStates.waiting_for_nickname_add)


@router.message(MasterManageStates.waiting_for_nickname_add)
async def m_force_nick(message: types.Message, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_force_nick(message, state, session)
    if not await check_google_sheet(message.text):
        return await message.answer("❌ Невалидный ник.")
    await state.update_data(nick=message.text)
    stmt = select(QueueType).filter_by(is_active=True)
    result = await session.execute(stmt)
    queues = result.scalars().all()
    kb = [
        [types.InlineKeyboardButton(text=q.name, callback_data=f"f_add_{q.id}")]
        for q in queues
    ]
    await message.answer("Куда?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(MasterManageStates.waiting_for_queue_add)


@router.callback_query(F.data.startswith("f_add_"))
async def m_force_add_queue_select(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_force_add_queue_select(callback, state, session)
    qid = int(callback.data.split("_")[2])
    q = await session.get(QueueType, qid)

    # Store context
    await state.update_data(qid=qid, action_type="single")

    # Ask for Mode
    kb = [
        [types.InlineKeyboardButton(text="1️⃣ Разовая запись", callback_data="m_mode_once")],
        [types.InlineKeyboardButton(text="🔄 Авто-запись", callback_data="m_mode_auto")],
    ]
    if q.name == "Цилинь":
        # Force Once
        await finalize_add(callback, state, qid, "single", session, auto_requeue=False)
    else:
        await callback.message.edit_text(
            f"Выбрана: {q.name}.\nВыберите режим:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
        )
        await state.set_state(MasterManageStates.waiting_for_mode)


@router.callback_query(F.data == "m_force_bulk")
async def m_bulk_add_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📝 **Отправь список ников** (каждый с новой строки):\n\n" "Ник1\nНик2\nНик3",
        parse_mode="Markdown",
        reply_markup=get_back_btn("m_force_add"),
    )
    await state.set_state(MasterManageStates.waiting_for_bulk_list)


@router.message(MasterManageStates.waiting_for_bulk_list)
async def m_bulk_input(message: types.Message, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_bulk_input(message, state, session)
    raw = message.text
    nicks = [line.strip() for line in raw.split("\n") if line.strip()]

    if not nicks:
        return await message.answer("❌ Список пуст.", reply_markup=get_back_btn("m_force_add"))

    # Validate? Optional. Let's assume Master knows what they do.
    await state.update_data(bulk_nicks=nicks)

    stmt = select(QueueType)
    result = await session.execute(stmt)
    queues = result.scalars().all()
    kb = [
        [types.InlineKeyboardButton(text=q.name, callback_data=f"f_bulk_{q.id}")]
        for q in queues
    ]
    await message.answer(
        f"Найдено ников: {len(nicks)}. Куда их добавить?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data.startswith("f_bulk_"))
async def m_bulk_add_queue_select(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_bulk_add_queue_select(callback, state, session)
    qid = int(callback.data.split("_")[2])
    q = await session.get(QueueType, qid)

    await state.update_data(qid=qid, action_type="bulk")

    # Ask for Mode
    kb = [
        [types.InlineKeyboardButton(text="1️⃣ Разовая запись", callback_data="m_mode_once")],
        [types.InlineKeyboardButton(text="🔄 Авто-запись", callback_data="m_mode_auto")],
    ]

    if q.name == "Цилинь":
        await finalize_add(callback, state, qid, "bulk", session, auto_requeue=False)
    else:
        await callback.message.edit_text(
            f"Выбрана: {q.name}.\nВыберите режим для СПИСКА:",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb),
        )
        await state.set_state(MasterManageStates.waiting_for_mode)


@router.callback_query(F.data.startswith("m_mode_"))
async def m_force_mode_select(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_force_mode_select(callback, state, session)
    mode = callback.data.split("_")[2]  # once / auto
    auto_requeue = mode == "auto"

    data = await state.get_data()
    qid = data["qid"]
    action_type = data["action_type"]

    await finalize_add(callback, state, qid, action_type, session, auto_requeue)


async def finalize_add(event, state, qid, action_type, session: AsyncSession = None, auto_requeue = False):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await finalize_add(event, state, qid, action_type, session, auto_requeue)
    data = await state.get_data()
    message = event.message if isinstance(event, types.CallbackQuery) else event

    q = await session.get(QueueType, qid)
    q_name = q.name if q else "Que"
    master_username = event.from_user.username

    nicks = []
    if action_type == "single":
        nicks.append(data["nick"])
    else:
        nicks = data["bulk_nicks"]

    added_count = 0
    mode_str = " (Авто)" if auto_requeue else ""

    for nick in nicks:
        stmt_char = select(Character).filter_by(nickname=nick)
        result_char = await session.execute(stmt_char)
        char = result_char.scalars().first()
        if char:
            uid = char.user_id
            stmt_main = select(Character).filter_by(user_id=char.user_id, is_main=True)
            result_main = await session.execute(stmt_main)
            main_char = result_main.scalars().first()
            main_nick = main_char.nickname if main_char else nick
        else:
            uid = None
            main_nick = nick

        session.add(QueueEntry(user_id=uid, queue_type_id=qid, character_name=nick, auto_requeue=auto_requeue))
        asyncio.create_task(log_reward_to_sheet(q_name, main_nick, nick, master_username, f"👑 Мастер{mode_str}"))
        added_count += 1

    await session.commit()

    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(
            f"✅ Добавлено {added_count} персонажей в {q_name}{mode_str}.", reply_markup=get_master_menu()
        )
    else:
        await message.answer(
            f"✅ Добавлено {added_count} персонажей в {q_name}{mode_str}.", reply_markup=get_master_menu()
        )

    await state.clear()


@router.callback_query(F.data == "m_force_del")
async def m_force_del(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_force_del(callback, session)
    stmt = select(QueueType)
    result = await session.execute(stmt)
    queues = result.scalars().all()
    kb = []
    for q in queues:
        stmt_count = select(func.count(QueueEntry.id)).filter_by(queue_type_id=q.id)
        result_count = await session.execute(stmt_count)
        if result_count.scalar() > 0:
            kb.append([types.InlineKeyboardButton(text=f"{q.name}", callback_data=f"sel_del_{q.id}")])
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text("❌ Выбери очередь:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data.startswith("sel_del_"))
async def m_force_del_list(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_force_del_list(callback, session)
    qid = int(callback.data.split("_")[2])
    await render_force_del_list(callback, qid, session)


async def render_force_del_list(event, qid, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await render_force_del_list(event, qid, session)
    message = event.message if isinstance(event, types.CallbackQuery) else event
    stmt = select(QueueEntry).filter_by(queue_type_id=qid)
    result = await session.execute(stmt)
    entries = result.scalars().all()
    kb = [[types.InlineKeyboardButton(text=f"❌ {e.character_name}", callback_data=f"kill_{e.id}")] for e in entries]
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await message.edit_text("Кого удалить?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data.startswith("kill_"))
async def m_kill(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_kill(callback, session)
    eid = int(callback.data.split("_")[1])
    e = await session.get(QueueEntry, eid, options=[selectinload(QueueEntry.queue)])
    if e:
        qid = e.queue_type_id
        asyncio.create_task(
            log_reward_to_sheet(
                e.queue.name, e.character_name, e.character_name, callback.from_user.username, "⛔ Кик Мастером"
            )
        )
        await session.delete(e)
        await session.commit()
        await callback.answer("✅ Удалено.")
        await render_force_del_list(callback, qid, session)
    else:
        await callback.answer("Уже удален.")


@router.callback_query(F.data == "m_global_log")
async def m_global_log(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_global_log(callback, session)
    stmt = select(RewardHistory).order_by(RewardHistory.timestamp.desc()).limit(15)
    result = await session.execute(stmt)
    hist = result.scalars().all()
    text = "🗄 <b>Лог последних выдач:</b>\n\n" + ("Архив пуст." if not hist else "")
    for h in hist:
        text += f"• <code>{h.timestamp.strftime('%d.%m')}</code> <b>{h.character_name}</b> → {h.queue_name}\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_btn("menu_master"))


# --- ОБЪЯВЛЕНИЯ (BROADCAST) ---
# Вспомогательные функции для шедулера
async def run_broadcast(ann_id, bot_instance):
    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        ann = await session.get(ScheduledAnnouncement, ann_id)
        if not ann or not ann.is_active:
            return
            
        from database import Player
        result = await session.execute(
            select(User).join(Player, Player.user_id == User.id).where(Player.in_clan == 1).distinct()
        )
        users = result.scalars().all()
        
        for u in users:
            try:
                await bot_instance.send_message(u.telegram_id, f"📢 <b>ОБЪЯВЛЕНИЕ</b>\n\n{ann.text}", parse_mode="HTML")
            except Exception:
                pass
        if ann.schedule_type == "once_future":
            ann.is_active = False
            await session.commit()


def schedule_job(ann, bot_instance):
    job_id = f"ann_{ann.id}"
    try:
        if ann.schedule_type == "daily":
            h, m = map(int, ann.run_time.split(":"))
            scheduler.add_job(
                run_broadcast, "cron", hour=h, minute=m, id=job_id, replace_existing=True, args=[ann.id, bot_instance]
            )
        elif ann.schedule_type == "weekly":
            h, m = map(int, ann.run_time.split(":"))
            scheduler.add_job(
                run_broadcast,
                "cron",
                day_of_week=ann.days_of_week,
                hour=h,
                minute=m,
                id=job_id,
                replace_existing=True,
                args=[ann.id, bot_instance],
            )
        elif ann.schedule_type == "once_future":
            dt = datetime.strptime(ann.run_time, "%d.%m.%Y %H:%M")
            datetime.strptime(ann.run_time, "%d.%m.%Y %H:%M")
            dt = datetime.strptime(ann.run_time, "%d.%m.%Y %H:%M")
            dt_msk = MSK.localize(dt)
            scheduler.add_job(
                run_broadcast, "date", run_date=dt_msk, id=job_id, replace_existing=True, args=[ann.id, bot_instance]
            )
    except Exception as e:
        print(f"❌ Error scheduling {job_id}: {e}")


@router.callback_query(F.data == "m_announce")
async def m_ann_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📢 Текст объявления:", reply_markup=get_back_btn("menu_master"))
    await state.set_state(AnnounceStates.waiting_for_text)


# --- AFK LIST ---
@router.callback_query(F.data == "m_afk_list")
async def m_afk_list(callback: types.CallbackQuery, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_afk_list(callback, session)
    now = get_msk_now()
    # Find active AFKs
    # Ideally logic: end_date >= now or (start <= now <= end) ?
    # Let's show all valid future/present periods.
    # filter(User.afk_end >= now) basically.

    stmt = select(User).filter(User.afk_end >= now).options(selectinload(User.characters))
    result = await session.execute(stmt)
    users = result.scalars().all()

    text = "🛌 <b>Список текущих и будущих AFK:</b>\n\n"
    if not users:
        text += "<i>Никого нет.</i>"
    else:
        for u in users:
            start = u.afk_start.strftime("%d.%m") if u.afk_start else "??"
            end = u.afk_end.strftime("%d.%m") if u.afk_end else "??"
            # Fix: User has no nickname, find main char
            main_char = next((c for c in u.characters if c.is_main), None)
            display_name = (
                main_char.nickname if main_char else (u.characters[0].nickname if u.characters else f"User {u.id}")
            )
            text += f"👤 <b>{display_name}</b> (@{u.username or 'no_user'}): {start} - {end}\n"

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_btn("menu_master"))


# --- ADMIN AFK SETTING ---



@router.callback_query(F.data.startswith("m_afk_set_"))
async def m_afk_admin_start(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_afk_admin_start(callback, state, session)
    parts = callback.data.split("_")
    uid, page = int(parts[3]), int(parts[4])
    user = await session.get(User, uid)
    if not user:
        return await callback.answer("Ошибка user")

    await state.update_data(target_uid=uid, page=page)
    await callback.message.edit_text(
        f"📅 <b>AFK для {user.username}: Дата НАЧАЛА</b>\n\n"
        "Выберите вариант или напишите дату вручную в формате <code>ДД.ММ</code> или <code>ДД.ММ.ГГГГ</code>.",
        parse_mode="HTML",
        reply_markup=get_afk_start_kb(),
    )
    await state.set_state(MasterManageStates.waiting_for_afk_start)


@router.callback_query(MasterManageStates.waiting_for_afk_start, F.data.startswith("afk_date_"))
async def m_afk_admin_date_click(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[2]
    now = get_msk_now()
    if action == "today":
        dt = now
    elif action == "tomorrow":
        dt = now + timedelta(days=1)

    await state.update_data(start_date=dt)
    await callback.answer()
    await m_afk_admin_ask_end(callback.message, state)


@router.message(MasterManageStates.waiting_for_afk_start)
async def m_afk_admin_date_manual(message: types.Message, state: FSMContext):
    dt = parse_date_input(message.text)
    if not dt:
        return await message.answer("⚠️ Неверный формат (ДД.ММ или ДД.ММ.ГГГГ)", reply_markup=get_afk_start_kb())
    await state.update_data(start_date=dt)
    await m_afk_admin_ask_end(message, state)


async def m_afk_admin_ask_end(message, state):
    msg = message if isinstance(message, types.Message) else message.message
    func = msg.edit_text if isinstance(message, types.CallbackQuery) else msg.answer
    await func("🏁 <b>Дата ОКОНЧАНИЯ отсутствия:</b>", parse_mode="HTML", reply_markup=get_afk_end_kb())
    await state.set_state(MasterManageStates.waiting_for_afk_end)


@router.callback_query(MasterManageStates.waiting_for_afk_end, F.data.startswith("afk_dur_"))
async def m_afk_admin_dur_click(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_afk_admin_dur_click(callback, state, session)
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

    await m_afk_admin_finish(callback, state, start_dt, end_dt, session=session)


@router.message(MasterManageStates.waiting_for_afk_end)
async def m_afk_admin_dur_manual(message: types.Message, state: FSMContext, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_afk_admin_dur_manual(message, state, session)
    data = await state.get_data()
    start_dt = data.get("start_date")
    end_dt = parse_date_input(message.text)

    # Validation logic same as user
    if not end_dt:
        return await message.answer("⚠️ Неверный формат.", reply_markup=get_afk_end_kb())
    if end_dt < start_dt:
        return await message.answer("⚠️ Дата окончания раньше начала.", reply_markup=get_afk_end_kb())

    uid = data["target_uid"]
    page = data["page"]
    user = await session.get(User, uid)

    user.afk_start = start_dt
    user.afk_end = end_dt
    session.add(AFKHistory(user_id=user.id, start_date=start_dt, end_date=end_dt))
    await session.commit()

    await message.answer(f"✅ AFK установлен для {user.username or user.telegram_id}.")
    kb = [[types.InlineKeyboardButton(text="🔙 К профилю", callback_data=f"m_u_manage_{uid}_{page}")]]
    await message.answer("Вернуться:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    await state.clear()


async def m_afk_admin_finish(callback, state, start_dt, end_dt, session: AsyncSession = None):
    if not session:
        from database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return await m_afk_admin_finish(callback, state, start_dt, end_dt, session)
    data = await state.get_data()
    uid = data["target_uid"]
    page = data["page"]
    user = await session.get(User, uid)

    user.afk_start = start_dt
    user.afk_end = end_dt
    session.add(AFKHistory(user_id=user.id, start_date=start_dt, end_date=end_dt))
    await session.commit()

    await callback.answer("✅ AFK установлен.")
    await render_user_manage(callback, uid, page, session)
    await state.clear()



# --- ОБЪЯВЛЕНИЯ (BROADCAST) ---


@router.message(AnnounceStates.waiting_for_text)
async def m_ann_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    kb = [
        [types.InlineKeyboardButton(text="⚡ Прямо сейчас", callback_data="ann_now")],
        [types.InlineKeyboardButton(text="📅 Разово в будущем", callback_data="ann_future")],
        [types.InlineKeyboardButton(text="⏰ Ежедневно", callback_data="ann_daily")],
        [types.InlineKeyboardButton(text="📆 По дням недели", callback_data="ann_weekly")],
    ]
    await message.answer("Когда отправить?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(AnnounceStates.waiting_for_type)


@router.callback_query(F.data.startswith("ann_"))
async def m_ann_type(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    atype = callback.data.split("_")[1]
    if atype == "now":
        data = await state.get_data()
        ann = ScheduledAnnouncement(text=data["text"], schedule_type="once_now", run_time="now", is_active=True)
        session.add(ann)
        await session.commit()
        await run_broadcast(ann.id, callback.bot)
        await callback.message.edit_text("✅ Отправлено.", reply_markup=get_master_menu())
        await state.clear()
    elif atype == "future":
        await callback.message.edit_text(
            "📅 Формат: `ДД.ММ.ГГГГ ЧЧ:ММ`", parse_mode="Markdown", reply_markup=get_back_btn("menu_master")
        )
        await state.set_state(AnnounceStates.waiting_for_datetime)
    elif atype == "daily":
        await state.update_data(days=[])
        await callback.message.edit_text(
            "⏰ Формат: `ЧЧ:ММ`", parse_mode="Markdown", reply_markup=get_back_btn("menu_master")
        )
        await state.set_state(AnnounceStates.waiting_for_time_only)
    elif atype == "weekly":
        await state.update_data(days=[])
        await callback.message.edit_text("📆 Дни недели:", reply_markup=get_weekdays_kb([]))
        await state.set_state(AnnounceStates.waiting_for_days)


@router.message(AnnounceStates.waiting_for_datetime)
async def process_future_datetime(message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        dt = message.text.strip()
        datetime.strptime(dt, "%d.%m.%Y %H:%M")
        data = await state.get_data()
        ann = ScheduledAnnouncement(text=data["text"], schedule_type="once_future", run_time=dt, is_active=True)
        session.add(ann)
        await session.commit()
        schedule_job(ann, message.bot)
        await message.answer(f"✅ Запланировано на {dt}", reply_markup=get_master_menu())
        await state.clear()
    except Exception:
        await message.answer("❌ Формат: ДД.ММ.ГГГГ ЧЧ:ММ")


@router.callback_query(F.data.startswith("toggle_day_"))
async def toggle_day(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split("_")[2]
    data = await state.get_data()
    days = data.get("days", [])
    if code in days:
        days.remove(code)
    else:
        days.append(code)
    await state.update_data(days=days)
    await callback.message.edit_reply_markup(reply_markup=get_weekdays_kb(days))


@router.callback_query(F.data == "days_confirm")
async def confirm_days(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("days", []):
        return await callback.answer("Выберите дни!", show_alert=True)
    await callback.message.edit_text(
        "⏰ Формат: `ЧЧ:ММ`", parse_mode="Markdown", reply_markup=get_back_btn("menu_master")
    )
    await state.set_state(AnnounceStates.waiting_for_time_only)


@router.message(AnnounceStates.waiting_for_time_only)
async def process_time_only(message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        t_str = message.text.strip()
        datetime.strptime(t_str, "%H:%M")
        data = await state.get_data()
        days_list = data.get("days", [])
        sch_type, days_str = ("weekly", ",".join(days_list)) if days_list else ("daily", None)
        ann = ScheduledAnnouncement(
            text=data["text"], schedule_type=sch_type, run_time=t_str, days_of_week=days_str, is_active=True
        )
        session.add(ann)
        await session.commit()
        schedule_job(ann, message.bot)
        await message.answer(f"✅ Расписание создано: {t_str}", reply_markup=get_master_menu())
        await state.clear()
    except Exception:
        await message.answer("❌ Формат: ЧЧ:ММ")


@router.callback_query(F.data == "m_schedule")
async def m_show_schedule(callback: types.CallbackQuery, session: AsyncSession):
    stmt = select(ScheduledAnnouncement).filter_by(is_active=True)
    result = await session.execute(stmt)
    tasks = result.scalars().all()
    text = "🗓 <b>Активные задачи:</b>\n\n" + ("Пусто" if not tasks else "")
    kb = []
    for t in tasks:
        desc = (
            "⏰ Ежедневно"
            if t.schedule_type == "daily"
            else (f"📆 {t.days_of_week}" if t.schedule_type == "weekly" else f"📅 {t.run_time}")
        )
        text += f"{desc} в {t.run_time} — {(t.text or '')[:10]}...\n"
        kb.append([types.InlineKeyboardButton(text=f"❌ Удалить ({desc})", callback_data=f"del_sch_{t.id}")])
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")])
    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data.startswith("del_sch_"))
async def m_del_schedule(callback: types.CallbackQuery, session: AsyncSession):
    aid = int(callback.data.split("_")[2])
    task = await session.get(ScheduledAnnouncement, aid)
    if task:
        task.is_active = False
        await session.commit()
        try:
            scheduler.remove_job(f"ann_{aid}")
        except JobLookupError:
            pass
        await callback.answer("Отключено.")
        await m_show_schedule(callback, session)
    else:
        await m_show_schedule(callback, session)


# --- БЭКАП СИСТЕМА (NEW) ---
@router.callback_query(F.data == "m_backup_menu")
async def m_backup_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💾 **Управление бэкапами**\nВыберите действие:", parse_mode="Markdown", reply_markup=get_backup_menu_kb()
    )


@router.callback_query(F.data == "m_bk_create")
async def m_bk_create(callback: types.CallbackQuery):
    await callback.message.edit_text("⏳ Создаю бэкап...", reply_markup=None)

    # Run sync function in executor or just sync if fast
    success = perform_backup("manual_user")

    if success:
        await callback.message.answer("✅ Бэкап успешно создан!", reply_markup=get_backup_menu_kb())
        # Ideally edit previous message, but "answer" creates new bottom.
        # Let's try to delete loading msg?
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await callback.message.edit_text("❌ Ошибка при создании бэкапа.", reply_markup=get_backup_menu_kb())


@router.callback_query(F.data.startswith("m_bk_list:"))
async def m_bk_list(callback: types.CallbackQuery):
    try:
        page = int(callback.data.split(":")[1])
    except Exception:
        page = 0

    # Get files
    import glob
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
    files = glob.glob(os.path.join(backup_dir, "guild_bot_*.*"))
    files = [f for f in files if f.endswith(".db") or f.endswith(".sql") or f.endswith(".bak")]
    files.sort(key=os.path.getmtime, reverse=True)  # Newest first

    files = [os.path.basename(f) for f in files]

    if not files:
        return await callback.message.edit_text("📂 Бэкапов не найдено.", reply_markup=get_back_btn("m_backup_menu"))

    await callback.message.edit_text(
        f"📂 **Список бэкапов** (Всего: {len(files)})",
        parse_mode="Markdown",
        reply_markup=get_backups_list_kb(files, page),
    )


@router.callback_query(F.data.startswith("m_bk_open:"))
async def m_bk_open(callback: types.CallbackQuery):
    filename = callback.data.split(":")[1]

    # Size info
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
    filepath = os.path.join(backup_dir, filename)

    if not os.path.exists(filepath):
        return await callback.answer("Файл не найден (возможно удален).", show_alert=True)

    size_mb = os.path.getsize(filepath) / (1024 * 1024)

    text = f"📄 **Файл:** `{filename}`\n📦 **Размер:** {size_mb:.2f} MB\n\nЧто сделать?"
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_backup_manage_kb(filename))


@router.callback_query(F.data.startswith("m_bk_down:"))
async def m_bk_download(callback: types.CallbackQuery):
    filename = callback.data.split(":")[1]
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
    filepath = os.path.join(backup_dir, filename)

    if not os.path.exists(filepath):
        return await callback.answer("Файл нет.")

    await callback.message.answer_document(FSInputFile(filepath), caption=f"📦 {filename}")
    await callback.answer("Отправлено!")


@router.callback_query(F.data.startswith("m_bk_del:"))
async def m_bk_delete(callback: types.CallbackQuery):
    filename = callback.data.split(":")[1]
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
    filepath = os.path.join(backup_dir, filename)

    try:
        os.remove(filepath)
        await callback.answer("🗑 Удалено.")
        await m_bk_list(callback)  # Return to list
    except Exception as e:
        await callback.answer(f"Ошибка удаления: {e}", show_alert=True)


@router.callback_query(F.data.startswith("m_bk_rest:"))
async def m_bk_restore_ask(callback: types.CallbackQuery):
    filename = callback.data.split(":")[1]
    text = (
        f"⚠️ **ВНИМАНИЕ! ВОССТАНОВЛЕНИЕ БД** ⚠️\n\n"
        f"Вы хотите восстановить базу из файла:\n`{filename}`\n\n"
        "ПОСЛЕДСТВИЯ:\n"
        "1. Текущая база будет перезаписана (данные после бэкапа пропадут).\n"
        "2. Перед этим будет создан авто-бэкап текущего состояния.\n"
        "3. **Бот будет ПЕРЕЗАГРУЖЕН**, чтобы применить изменения.\n\n"
        "Вы уверены?"
    )

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_restore_confirm_kb(filename))


@router.callback_query(F.data.startswith("m_bk_do_rest:"))
async def m_bk_restore_do(callback: types.CallbackQuery):
    filename = callback.data.split(":")[1]
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
    filepath = os.path.join(backup_dir, filename)

    if not os.path.exists(filepath):
        return await callback.answer("Ошибка: Файл бэкапа не найден.", show_alert=True)

    await callback.message.edit_text(
        "⏳ **Восстановление...**\n1. Создаю safety-бэкап...\n2. Заменяю базу...\n3. Перезагружаюсь...",
        parse_mode="Markdown",
    )

    # 1. Perform restore (it handles safety backup internally now, but our script is designed for CLI/import.
    # Let's call restore logic.
    try:
        # We need to ensure we call the function properly.
        # scripts.restore_db.restore(target_backup) logic:
        # It prints to stdout. We want it to be silent or log?
        # Let's trust it.
        from scripts.restore_db import restore as restore_db_func
        restore_db_func(filepath, skip_confirm=True)  # This assumes it works and doesn't exit sys.

        await callback.message.answer("✅ **УСПЕШНО!**\nБот перезагружается прямо сейчас...")

        # 2. RESTART BOT
        # We use sys.executable and sys.argv to restart the process
        # Note: This works if running via python direct. If docker/bat, might be tricky.
        # But 'run.bat' runs 'python main.py'.
        # So restarting this python process should be enough if the outer loop isn't blocking.
        # If run via BAT loop (cmd /k), exiting python simply ends it? No, cmd /k keeps window open.
        # We need to re-execute python.

        # Simple restart:
        # os.execv(sys.executable, ['python'] + sys.argv)
        # sys.argv[0] is typically the script name.

        print("RESTARTING BOT BY ADMIN REQUEST...")
        os.execv(sys.executable, [sys.executable, "main.py"])

    except Exception as e:
        await callback.message.answer(f"❌ **КРИТИЧЕСКАЯ ОШИБКА:** {e}")


# --- PUBLIC LOG SETTINGS ---
@router.callback_query(F.data == "m_log_settings")
async def m_log_settings_menu(callback: types.CallbackQuery, session: AsyncSession):
    enabled = await get_setting(session, "public_log_enabled")
    chan_id = await get_setting(session, "public_log_channel_id")
    thread_id = await get_setting(session, "public_log_thread_id")

    status_icon = "✅ ВКЛ" if enabled == "true" else "❌ ВЫКЛ"

    chan_display = chan_id if chan_id else "Не задан"
    if chan_id and thread_id:
        chan_display += f" (Топик: {thread_id})"

    text = (
        f"📝 <b>Настройка сводки по выдаче КХ ресов в группе клана</b>\n\n"
        f"Статус: <b>{status_icon}</b>\n"
        f"Канал/Группа: <code>{chan_display}</code>\n\n"
        "При рассылке уведомлений бот будет отправлять сводный отчет в этот канал.\n\n"
        "⚠️ <b>Важно:</b> Бот должен быть <b>Администратором</b> в этом канале/группе, чтобы писать сообщения!\n\n"
        "❓ <b>Как узнать ID канала/группы?</b>\n"
        "САМЫЙ ПРОСТОЙ СПОСОБ:\n"
        "1. Добавьте бота в нужную группу/канал (как админа).\n"
        "2. Напишите там команду <code>/id</code> (если это топик - пишите в топике).\n"
        "3. Бот ответит ID чата и ID топика.\n"
        "4. Введите сюда ID в формате: <code>ChatID:TopicID</code> (или просто ChatID, если нет топиков)."
    )

    kb = [
        [types.InlineKeyboardButton(text="✏️ Задать ID Канала/Топика", callback_data="m_set_log_chan")],
        [types.InlineKeyboardButton(text="🔄 Вкл/Выкл", callback_data="m_toggle_log")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="m_menu_system")],
    ]
    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data == "m_toggle_log")
async def m_toggle_log(callback: types.CallbackQuery, session: AsyncSession):
    was = await get_setting(session, "public_log_enabled")
    new_val = "false" if was == "true" else "true"
    await set_setting(session, "public_log_enabled", new_val)
    await m_log_settings_menu(callback, session)


@router.callback_query(F.data == "m_set_log_chan")
async def m_set_log_chan_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✏️ Введите <b>ID канала</b> (начинается с -100...).\nЕсли нужно слать в топик, введите: <code>ID_Чата:ID_Топика</code>",
        parse_mode="HTML",
        reply_markup=get_back_btn("m_log_settings"),
    )
    await state.set_state(MasterManageStates.waiting_for_log_channel_id)


@router.message(MasterManageStates.waiting_for_log_channel_id)
async def m_set_log_chan_save(message: types.Message, state: FSMContext, session: AsyncSession):
    val = message.text.strip()

    chat_id = val
    thread_id = None

    if ":" in val:
        parts = val.split(":")
        chat_id = parts[0].strip()
        thread_id = parts[1].strip()

    # Simple validation
    if not (chat_id.startswith("-100") or chat_id.startswith("@") or chat_id.replace("-", "").isdigit()):
        await message.answer(
            "⚠️ Похоже, это не ID канала. Попробуйте еще раз (-100...).", reply_markup=get_back_btn("m_log_settings")
        )
        return

    await set_setting(session, "public_log_channel_id", chat_id)
    if thread_id:
        await set_setting(session, "public_log_thread_id", thread_id)
    else:
        # Clear thread id if not provided
        await set_setting(session, "public_log_thread_id", "")

    await message.answer(
        f"✅ Канал сохранен: {chat_id}" + (f" (Топик: {thread_id})" if thread_id else ""),
        reply_markup=get_master_system_menu(),
    )

    # Try to verify?
    try:
        await message.bot.send_message(
            chat_id,
            "✅ Тестовое сообщение: Бот готов публиковать сводку по выдаче наград из очередей.",
            message_thread_id=thread_id,
        )
    except Exception as e:
        await message.answer(
            f"⚠️ Предупреждение: Не удалось отправить тестовое сообщение.\nОшибка: {e}\nУбедитесь, что бот админ в канале."
        )

    await state.clear()


# --- APPROVAL SYSTEM (NEW ACCESS) ---
@router.callback_query(F.data.startswith("appr:"))
async def m_process_approval(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    parts = callback.data.split(":")
    action = parts[1]  # ok, edit, no
    user_id = int(parts[2])

    # Optional parts
    reg_type = parts[3] if len(parts) > 3 else ""  # main_input, alt_input

    # Clean up message buttons first
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    target_user = await session.get(User, user_id)
    if not target_user:
        return await callback.answer("Пользователь не найден.", show_alert=True)

    # 1. Reject
    if action == "no":
        try:
            await bot.send_message(
                target_user.telegram_id, "❌ <b>Ваша заявка отклонена Мастером.</b>", parse_mode="HTML"
            )
        except Exception:
            pass

        # Clear pending state
        target_user.pending_request_nick = None
        await session.commit()

        await callback.message.answer(f"❌ Заявка отклонена ({target_user.username}).")
        await callback.answer()
        return

    # 2. Approve OK (Direct)
    if action == "ok":
        nick = ":".join(parts[4:])

        # VALIDATION: Check if request was cancelled (main_input only)
        if reg_type == "main_input":
            if target_user.pending_request_nick != nick:
                try:
                    await callback.message.edit_text(
                        f"⚠️ <b>Заявка неактуальна.</b>\nПользователь отменил её или изменил ник.\n(Запрос: {nick}, Текущий: {target_user.pending_request_nick})"
                    )
                except Exception:
                    pass
                await callback.answer("Заявка отменена пользователем.", show_alert=True)
                return

        await finalize_approval(callback, target_user, nick, reg_type, session)

    # 3. Approve Edit (Ask for nick)
    if action == "edit":
        # Need to ask Master for nick.
        await callback.message.answer(
            f"✍️ Введите правильный ник для {target_user.username}:", reply_markup=get_back_btn("menu_master")
        )
        await state.update_data(target_uid=user_id, reg_type=reg_type)
        await state.set_state(MasterManageStates.waiting_for_approve_edit)


@router.message(MasterManageStates.waiting_for_approve_edit)
async def m_approve_edit_save(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    uid = data["target_uid"]
    reg_type = data["reg_type"]
    nick = message.text.strip()

    target_user = await session.get(User, uid)
    if target_user:
        await finalize_approval(message, target_user, nick, reg_type, session)

    await state.clear()


async def finalize_approval(event, target_user, nick, reg_type, session: AsyncSession):
    # Logic similar to finish_main_input / finish_alt_input
    # But since we are in admin.py and can't easy import from user.py, we replicate core logic.

    # 1. Main Char Logic
    if reg_type == "main_input":
        stmt_existing = select(Character).filter_by(user_id=target_user.id, nickname=nick)
        result_existing = await session.execute(stmt_existing)
        existing_char = result_existing.scalars().first()

        stmt_old = select(Character).filter_by(user_id=target_user.id, is_main=True)
        result_old = await session.execute(stmt_old)
        old_main = result_old.scalars().first()

        if not old_main:
            if existing_char:
                existing_char.is_main = True
                msg = f"🆙 Твин <b>{nick}</b> повышен до Основы (Мастером)!"
            else:
                session.add(Character(user_id=target_user.id, nickname=nick, is_main=True))
                msg = f"✅ Основа установлена: <b>{nick}</b> (Одобрено Мастером)"

        else:
            # Logic for changing main is complex (confirmations etc).
            # Simplify for Master Force Add: Just do it.
            old_main.is_main = False
            if existing_char:
                existing_char.is_main = True
            else:
                session.add(Character(user_id=target_user.id, nickname=nick, is_main=True))
            msg = f"✅ Основа сменена на <b>{nick}</b> (Мастером)."

            # Queue updates
            stmt_entries = select(QueueEntry).filter_by(user_id=target_user.id)
            result_entries = await session.execute(stmt_entries)
            entries = result_entries.scalars().all()
            for e in entries:
                if e.character_name != nick:
                    e.character_name = nick

    # 2. Alt Logic
    elif reg_type == "alt_input":
        stmt_existing = select(Character).filter_by(user_id=target_user.id, nickname=nick)
        result_existing = await session.execute(stmt_existing)
        if result_existing.scalars().first():
            msg = f"⚠️ Твин {nick} уже был у пользователя."
        else:
            session.add(Character(user_id=target_user.id, nickname=nick, is_main=False))
            msg = f"✅ Твин добавлен: <b>{nick}</b> (Одобрено Мастером)"

    # Sync with Player table for website
    from database import Player
    from sqlalchemy import func
    stmt_p = select(Player).where(func.lower(Player.nickname) == func.lower(nick))
    result_p = await session.execute(stmt_p)
    player_obj = result_p.scalars().first()
    if player_obj:
        # is_main == True -> is_alt = False
        # reg_type == "main_input" -> is_alt = False
        # reg_type == "alt_input" -> is_alt = True
        player_obj.is_alt = (reg_type == "alt_input")
        player_obj.user_id = target_user.id
        await session.commit()

    # Clear pending state
    target_user.pending_request_nick = None
    await session.commit()

    # Notify User with Main Menu
    try:
        # Generate the main menu text with the approval message as header
        menu_text, restricted = await get_menu_text(session, target_user, custom_title=msg)
        
        main_role_id = await get_user_main_role_id(session, target_user)
        await update_user_menu_button(target_user.telegram_id, main_role_id)
        
        main_menu_kb = get_main_menu(target_user, restricted, main_role_id=main_role_id)

        await bot.send_message(target_user.telegram_id, menu_text, parse_mode="HTML", reply_markup=main_menu_kb)
    except Exception:
        pass

    # Notify Master
    kb_master_nav = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main")],
            [types.InlineKeyboardButton(text="👑 Панель Мастера", callback_data="menu_master")],
        ]
    )

    if isinstance(event, types.CallbackQuery):
        await event.message.answer(f"✅ Успешно: {target_user.username} -> {nick}", reply_markup=kb_master_nav)
    else:
        await event.answer(f"✅ Успешно: {target_user.username} -> {nick}", reply_markup=kb_master_nav)

    # Notify Other Masters
    approver_id = event.from_user.id
    result_appr = await session.execute(select(User).filter_by(telegram_id=approver_id))
    approver_user = result_appr.scalars().first()
    approver_name = f"@{approver_user.username}" if (approver_user and approver_user.username) else "Мастер"

    result_others = await session.execute(select(User).filter(User.is_master, User.telegram_id != approver_id))
    other_masters = result_others.scalars().all()
    for m in other_masters:
        try:
            await event.bot.send_message(
                m.telegram_id,
                f"ℹ️ <b>{approver_name} одобрил заявку:</b>\nИгрок: {target_user.username or 'ID '+str(target_user.id)}\nНик: {nick}",
                parse_mode="HTML",
            )
        except Exception:
            pass


# --- ГРУППА КЛАНА ---

@router.message(Command("set_clan_group"))
async def cmd_set_clan_group(message: types.Message, session: AsyncSession):
    if not await is_master(session, message.from_user.id):
        return

    # If command argument is present, use it. Else use current chat.
    args = message.text.split()
    if len(args) > 1:
        chat_id = args[1]
    else:
        chat_id = message.chat.id

    await set_setting(session, "clan_chat_id", chat_id)
    await message.answer(
        f"✅ ID этой группы ({chat_id}) сохранен как Клановая Группа.\nТеперь бот будет приглашать сюда новичков и кикать тех, кто удалил всех персонажей."
    )


# --- VERIFICATION CODE SETTINGS ---
@router.callback_query(F.data == "m_verification")
async def m_verification_menu(callback: types.CallbackQuery, session: AsyncSession):
    code = await get_setting(session, "verification_code")
    status = f"✅ ВКЛ ({code})" if code else "❌ ВЫКЛ"

    text = f"🔐 <b>Код верификации</b>\nТекущий статус: {status}\n\nЕсли включено, бот будет требовать этот код при добавлении любого персонажа (основы или твина)."

    kb = [
        [types.InlineKeyboardButton(text="✏️ Задать код", callback_data="m_set_code")],
        [types.InlineKeyboardButton(text="❌ Отключить проверку", callback_data="m_disable_code")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_master")],
    ]
    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data == "m_set_code")
async def m_set_code_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🔐 Введите новый код верификации (любое слово или число):", reply_markup=get_back_btn("m_verification")
    )
    await state.set_state(MasterManageStates.waiting_for_code_setting)


@router.message(MasterManageStates.waiting_for_code_setting)
async def m_set_code_save(message: types.Message, state: FSMContext, session: AsyncSession):
    code = message.text.strip()
    await set_setting(session, "verification_code", code)
    await message.answer(
        f"✅ Код верификации установлен: <b>{code}</b>", parse_mode="HTML", reply_markup=get_master_menu()
    )
    await state.clear()


@router.callback_query(F.data == "m_disable_code")
async def m_disable_code(callback: types.CallbackQuery, session: AsyncSession):
    stmt = select(Settings).filter_by(key="verification_code")
    result = await session.execute(stmt)
    s = result.scalars().first()
    if s:
        await session.delete(s)
        await session.commit()

    await callback.answer("✅ Проверка кодом отключена.")
    await m_verification_menu(callback, session)


# @router.chat_member()
async def on_user_join(event: ChatMemberUpdated, session: AsyncSession):
    # Проверяем, что это вступление (был left/kicked/restricted -> стал member/creator/administrator)
    old = event.old_chat_member.status
    new = event.new_chat_member.status

    # Реагируем только на вступление (member)
    if new not in ["member", "administrator", "creator"]:
        return
    if old in ["member", "administrator", "creator"]:
        return  # Уже был в чате (смена прав)

    chat_id = await get_setting(session, "clan_chat_id")
    current_chat_id = str(event.chat.id)

    # Проверяем, что это целевая группа
    if not chat_id or str(chat_id) != current_chat_id:
        return

    user = event.new_chat_member.user
    if user.is_bot:
        return

    # Проверка по базе
    stmt_user = select(User).filter_by(telegram_id=user.id)
    result_user = await session.execute(stmt_user)
    db_user = result_user.scalars().first()
    has_chars = False

    if db_user:
        stmt_count = select(func.count(Character.id)).filter_by(user_id=db_user.id)
        result_count = await session.execute(stmt_count)
        if result_count.scalar() > 0:
            has_chars = True

    if not has_chars:
        try:
            await event.bot.ban_chat_member(event.chat.id, user.id)
            await event.bot.unban_chat_member(event.chat.id, user.id)
            await event.bot.send_message(
                event.chat.id,
                f"⛔ Пользователь {user.mention_html()} был исключен (нет персонажей в боте).",
                parse_mode="HTML",
            )
        except Exception as e:
            await event.bot.send_message(event.chat.id, f"⚠️ Не удалось кикнуть нелегала: {e}")
    else:
        # Можно поприветствовать
        pass
