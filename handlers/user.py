from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import asyncio

# Импорты из корня проекта
from database import session, User, Character, QueueEntry, QueueType, RewardHistory, ensure_user, get_user_active_queues, get_effective_limit_logic, get_setting
from keyboards import get_main_menu, get_back_btn, get_persistent_menu
from helpers import get_menu_text
from states import Registration
from utils import check_google_sheet, log_reward_to_sheet

router = Router()

# --- START ---
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user = ensure_user(message.from_user.id, message.from_user.username)
    if user.is_banned:
        return await message.answer("⛔ <b>Вы забанены.</b>", parse_mode="HTML")

    text = get_menu_text(user)
    # Send persistent keyboard separately or attach? usually attach to answer.
    # We send the inline menu message, AND a separate message (or same) with ReplyKeyboard? 
    # ReplyKeyboard cannot be combined with Inline in same message? 
    # Actually they can be separate messages. Inline is usually for interaction, Reply for global nav.
    # Let's send a "Welcome" with ReplyMarkup, and then the menu with Inline.
    
    await message.answer("👋", reply_markup=get_persistent_menu())
    await message.answer(text, reply_markup=get_main_menu(user), parse_mode="HTML")

@router.message(F.text == "🏠 Главное меню")
async def main_menu_text(message: types.Message):
    await cmd_start(message)

@router.callback_query(F.data == "back_to_main")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    if user.is_banned:
        return await callback.message.edit_text("⛔ Вы забанены.", parse_mode="HTML")
    
    text = get_menu_text(user)
    try:
        await callback.message.edit_text(text, reply_markup=get_main_menu(user), parse_mode="HTML")
    except:
        await callback.message.answer(text, reply_markup=get_main_menu(user), parse_mode="HTML")


# --- УПРАВЛЕНИЕ ПЕРСОНАЖАМИ ---

@router.callback_query(F.data == "menu_chars")
async def chars_menu(callback: types.CallbackQuery):
    # Получаем пользователя
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    
    kb = [
        [types.InlineKeyboardButton(text="➕ Добавить или изменить основу", callback_data="add_main")],
        [types.InlineKeyboardButton(text="➕ Добавить твина", callback_data="add_alt")],
        [types.InlineKeyboardButton(text="🗑 Удалить твина", callback_data="del_alt_menu")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ]
    
    # Генерируем текст с кастомным заголовком
    text = get_menu_text(user, custom_title="⚙️ <b>Управление персонажами:</b>")
    
    await callback.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

@router.callback_query(F.data == "add_main")
async def add_main_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✍️ Введи никнейм **ОСНОВЫ**:", reply_markup=get_back_btn("menu_chars"), parse_mode="Markdown")
    await state.set_state(Registration.waiting_for_main_nickname)

@router.message(Registration.waiting_for_main_nickname)
async def process_main_input_entry(message: types.Message, state: FSMContext):
    nick = message.text.strip()
    
    # Check if exists in DB
    is_known = await check_google_sheet(nick)
    await state.update_data(needs_approval=not is_known)
    
    code = get_setting("verification_code")
    # If code is required, OR if user is unknown (we always want code for unknown? User said "also ask code")
    # Actually user said "if nick not in base, also ask code".
    # So if code setting is enabled -> ask.
    # If code setting is DISABLED -> if unknown -> logic? 
    # Let's assume if code is disabled, we skip code. But user said "person should be in guild", implying code is the key.
    # If code is OFF, we probably should still ask for approval if unknown.
    
    if code:
        await state.update_data(temp_nick=nick, temp_action="main_input")
        text = "🔐 Введите код верификации:"
        if not is_known: text = "⚠️ Этого ника нет в базе.\n🔐 Введите код верификации, чтобы отправить заявку Мастеру:"
        
        await message.answer(text, reply_markup=get_back_btn("menu_chars"))
        await state.set_state(Registration.waiting_for_code)
        return

    # If NO code setting:
    if is_known:
        await finish_main_input(message, state, nick_override=nick)
    else:
        # Unknown + No Code => Send to Master directly? Or reject?
        # User imply code is necessary for proof. But if code is off...
        # Let's send to Master anyway.
        await send_approval_request(message, state, nick, "main_input")

async def finish_main_input(message: types.Message, state: FSMContext, nick_override=None):
    nick = nick_override if nick_override else message.text.strip()
    
    user = ensure_user(message.from_user.id, message.from_user.username)
    
    # Check if already exists (globally or for user?)
    # Nickname uniqueness is not strictly enforced in DB schema, but logically should be.
    # Check if this user already has main?
    
    existing = session.query(Character).filter_by(user_id=user.id, is_main=True).first()
    if existing:
        existing.is_main = False
        # Optional: rename old main to alt? 
        # For this bot logic: user can have only one main? or switch?
        # Usually we just set new main.
    
    # Check if nick taken by SOMEONE ELSE?
    taken = session.query(Character).filter_by(nickname=nick).first()
    if taken and taken.user_id != user.id:
        return await message.answer(f"⚠️ Ник <b>{nick}</b> уже занят другим пользователем.", parse_mode="HTML", reply_markup=get_back_btn("menu_chars"))
    
    if taken and taken.user_id == user.id:
        taken.is_main = True
        session.commit()
    else:
        session.add(Character(user_id=user.id, nickname=nick, is_main=True))
        session.commit()
        
    await message.answer(f"✅ Основа сохранена: <b>{nick}</b>", parse_mode="HTML", reply_markup=get_main_menu(user))
    await state.clear()

@router.callback_query(F.data == "add_alt")
async def add_alt_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✍️ Введи никнейм **ТВИНА**:", reply_markup=get_back_btn("menu_chars"), parse_mode="Markdown")
    await state.set_state(Registration.waiting_for_alt_nickname)

@router.message(Registration.waiting_for_alt_nickname)
async def process_alt_input_entry(message: types.Message, state: FSMContext):
    nick = message.text.strip()
    
    # Check Google
    is_known = await check_google_sheet(nick)
    await state.update_data(needs_approval=not is_known)

    code = get_setting("verification_code")
    if code:
        await state.update_data(temp_nick=nick, temp_action="alt_input")
        text = "🔐 Введите код верификации:"
        if not is_known: 
            text = ("⚠️ Возможно, этот персонаж уже вступил в гильдию, но в базе его ещё нет, либо в никнейме есть опечатки\n"
                    "🔐 Если этот персонаж есть в гильдии, и вы правильно ввели никнейм, введите код верификации (он указан в клан листе гильдии), чтобы отправить заявку Мастеру:")
        
        await message.answer(text, reply_markup=get_back_btn("menu_chars")) 
        await state.set_state(Registration.waiting_for_code)
        return

    if is_known:
        await finish_alt_input(message, state, nick_override=nick)
    else:
        await send_approval_request(message, state, nick, "alt_input")

# @router.message(Registration.waiting_for_alt_nickname)
async def finish_alt_input(message: types.Message, state: FSMContext, nick_override=None):
    nick = nick_override if nick_override else message.text.strip()
    
    # We retain basic checks but skip Google/Main check as they should be done in entry
    user = ensure_user(message.from_user.id, message.from_user.username)
    main_char = session.query(Character).filter_by(user_id=user.id, is_main=True).first()
    
    if not main_char:
         # Should not happen if pre-checked, but safe to keep
        return await message.answer("⛔ Сначала добавь <b>Основу</b>.", parse_mode="HTML", reply_markup=get_back_btn("menu_chars"))
    
    if session.query(Character).filter_by(user_id=user.id, nickname=nick).first():
        return await message.answer("⚠️ Уже добавлен.", reply_markup=get_back_btn("menu_chars"))

    session.add(Character(user_id=user.id, nickname=nick, is_main=False))
    session.commit()
    await message.answer(f"✅ Твин добавлен: <b>{nick}</b>", parse_mode="HTML", reply_markup=get_main_menu(user))
    await state.clear()

@router.message(Registration.waiting_for_code)
async def process_verification_code(message: types.Message, state: FSMContext):
    input_code = message.text.strip()
    correct_code = get_setting("verification_code")
    
    if correct_code and input_code.lower() != correct_code.lower():
        return await message.answer("❌ Неверный код! Попробуйте еще раз или нажмите Назад.", reply_markup=get_back_btn("menu_chars"))
    
    data = await state.get_data()
    nick = data.get("temp_nick")
    action = data.get("temp_action")
    needs_approval = data.get("needs_approval", False)
    
    if needs_approval:
        await send_approval_request(message, state, nick, action)
        return

    if action == "main_input":
        await finish_main_input(message, state, nick_override=nick)
    elif action == "alt_input":
        await finish_alt_input(message, state, nick_override=nick)
    else:
        await message.answer("Ошибка состояния. Начни заново.", reply_markup=get_main_menu(ensure_user(message.from_user.id, message.from_user.username)))
        await state.clear()

async def send_approval_request(message: types.Message, state: FSMContext, nick: str, action: str):
    # Find masters
    masters = session.query(User).filter_by(is_master=True).all()
    if not masters:
        await message.answer("⚠️ Нет Мастеров в сети. Попробуй позже.", reply_markup=get_main_menu(ensure_user(message.from_user.id, message.from_user.username)))
        await state.clear()
        return

    user = ensure_user(message.from_user.id, message.from_user.username)
    type_str = "ОСНОВА" if action == "main_input" else "ТВИН"
    user_link = f"<a href='tg://user?id={user.telegram_id}'>{user.username or 'Без ника'}</a>"
    
    text = f"🛡 <b>Заявка на добавление:</b>\n"
    text += f"Игрок: {user_link}\n"
    text += f"Ник: <code>{nick}</code> ({type_str})\n"
    text += "⚠️ <i>Этого ника нет в базе. Требуется подтверждение.</i>"

    kb = [
        [types.InlineKeyboardButton(text="✅ Принять", callback_data=f"appr:ok:{user.id}:{action}:{nick}")], 
        [types.InlineKeyboardButton(text="✏️ Исправить и принять", callback_data=f"appr:edit:{user.id}:{action}")],
        [types.InlineKeyboardButton(text="❌ Отказать", callback_data=f"appr:no:{user.id}")]
    ]
    
    count = 0
    for m in masters:
        try:
            # Save temp data in a temporary storage? logic is stateless in callback.
            # We pass data in callback_data. 
            await message.bot.send_message(m.telegram_id, text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
            count += 1
        except: pass
        
    if count > 0:
        await message.answer("⏳ <b>Заявка отправлена Мастеру.</b>\nОжидайте подтверждения.", parse_mode="HTML", reply_markup=get_main_menu(user))
    else:
        await message.answer("⚠️ Не удалось связаться с Мастером.", reply_markup=get_main_menu(user))
    
    await state.clear()

@router.callback_query(F.data == "del_alt_menu")
async def del_alt_menu(callback: types.CallbackQuery):
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    alts = session.query(Character).filter_by(user_id=user.id, is_main=False).all()
    if not alts: return await callback.answer("Нет твинов.", show_alert=True)
    kb = [[types.InlineKeyboardButton(text=f"❌ {c.nickname}", callback_data=f"del_c_{c.id}")] for c in alts]
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_chars")])
    await callback.message.edit_text("Кого удалить?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("del_c_"))
async def del_char_action(callback: types.CallbackQuery):
    cid = int(callback.data.split("_")[2])
    char = session.get(Character, cid)
    if not char: return await callback.answer("Не найден.")
    
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    entries = session.query(QueueEntry).filter_by(character_name=char.nickname).all()
    if entries:
        main_char = session.query(Character).filter_by(user_id=user.id, is_main=True).first()
        text = f"⚠️ Персонаж <b>{char.nickname}</b> записан в очередях ({len(entries)} шт.)!\n\n"
        kb = []
        if main_char:
            text += f"Я заменю его на основу: <b>{main_char.nickname}</b>."
            kb.append([types.InlineKeyboardButton(text=f"✅ Заменить на {main_char.nickname} и удалить", callback_data=f"conf_del_{cid}_swap")])
        else:
            text += "Он исчезнет из всех очередей."
            kb.append([types.InlineKeyboardButton(text="🗑 Удалить отовсюду", callback_data=f"conf_del_{cid}_kill")])
        kb.append([types.InlineKeyboardButton(text="🔙 Отмена", callback_data="menu_chars")])
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        nick = char.nickname
        session.delete(char)
        session.commit()
        await callback.answer(f"{nick} удален.")
        
        # Check for kick
        count = session.query(Character).filter_by(user_id=user.id).count()
        if count == 0:
            chat_id = get_setting('clan_chat_id')
            if chat_id:
                try:
                    await callback.bot.ban_chat_member(chat_id, user.telegram_id)
                    await callback.bot.unban_chat_member(chat_id, user.telegram_id)
                    await callback.message.answer("⚠️ Вы были исключены из группы клана, так как у вас не осталось активных персонажей.")
                except Exception as e:
                    print(f"Kick error: {e}")

        await del_alt_menu(callback)

@router.callback_query(F.data.startswith("conf_del_"))
async def confirm_del_char_complex(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    cid, action = int(parts[2]), parts[3]
    char = session.get(Character, cid)
    if not char: return await callback.answer("Уже удален.")
    
    nick_to_del, user_id = char.nickname, char.user_id
    user = session.get(User, user_id)
    entries = session.query(QueueEntry).filter_by(character_name=nick_to_del).all()
    
    for e in entries:
        q_name = e.queue.name
        if action == "swap":
            main_char = session.query(Character).filter_by(user_id=user_id, is_main=True).first()
            if main_char:
                e.character_name = main_char.nickname
                asyncio.create_task(log_reward_to_sheet(queue_name=q_name, main_nick=main_char.nickname, char_nick=main_char.nickname, manager_name=user.username, status=f"♻️ Авто-замена ({nick_to_del})"))
            else: session.delete(e)
        elif action == "kill":
            session.delete(e)
            asyncio.create_task(log_reward_to_sheet(queue_name=q_name, main_nick=nick_to_del, char_nick=nick_to_del, manager_name=user.username, status="❌ Ушел (удаление перса)"))

    session.delete(char)
    session.commit()
    
    # Check for kick
    count = session.query(Character).filter_by(user_id=user_id).count()
    if count == 0:
        chat_id = get_setting('clan_chat_id')
        if chat_id:
            try:
                await callback.bot.ban_chat_member(chat_id, user.telegram_id)
                await callback.bot.unban_chat_member(chat_id, user.telegram_id)
                await callback.message.answer("⚠️ Вы были исключены из группы клана, так как у вас не осталось активных персонажей.")
            except Exception as e:
                print(f"Kick error (complex): {e}")

    await callback.message.edit_text(f"✅ {nick_to_del} удален.", reply_markup=get_back_btn("menu_chars"))


# --- ОЧЕРЕДИ ---

@router.callback_query(F.data == "menu_join")
async def join_menu(callback: types.CallbackQuery):
    # Получаем пользователя для генерации текста
    user = ensure_user(callback.from_user.id, callback.from_user.username)

    queues = session.query(QueueType).filter_by(is_active=True).all()
    kb = []
    
    for q in queues:
        count = session.query(QueueEntry).filter_by(queue_type_id=q.id).count()
        status = "🔒 ЗАКРЫТА" if q.is_locked else f"({count})"
        kb.append([types.InlineKeyboardButton(text=f"{q.name} {status}", callback_data=f"view_q_{q.id}")])
        
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    
    # Генерируем текст с кастомным заголовком
    text = get_menu_text(user, custom_title="✍️ <b>Запись в очередь:</b>")
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("view_q_"))
async def view_queue(callback: types.CallbackQuery):
    qid = int(callback.data.split("_")[2])
    q = session.get(QueueType, qid)
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    entries = session.query(QueueEntry).filter_by(queue_type_id=qid).all()
    
    text = f"🛡 <b>Очередь: {q.name}</b>\n\n"
    if not entries: text += "<i>Пока пусто.</i>"
    else:
        for i, e in enumerate(entries, 1): text += f"{i}. {e.character_name}\n"
    
    kb = []
    user_entry = session.query(QueueEntry).filter_by(queue_type_id=qid, user_id=user.id).first()
    if user_entry: kb.append([types.InlineKeyboardButton(text="🏃 Выйти из очереди", callback_data=f"leave_q_{qid}")])
    else: kb.append([types.InlineKeyboardButton(text="✍️ Записаться", callback_data=f"pre_join_{qid}")])
    kb.append([types.InlineKeyboardButton(text="🔙 К списку", callback_data="menu_join")])
    try: await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))
    except: pass

@router.callback_query(F.data.startswith("pre_join_"))
async def pre_join(callback: types.CallbackQuery):
    qid = int(callback.data.split("_")[2])
    q = session.get(QueueType, qid)
    if q.is_locked: return await callback.answer("⛔ Очередь закрыта Мастером!", show_alert=True)
    
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    chars = session.query(Character).filter_by(user_id=user.id).all()
    if not chars: return await callback.answer("Нет персонажей!", show_alert=True)
    
    kb = [[types.InlineKeyboardButton(text=f"{'👑' if c.is_main else '👤'} {c.nickname}", callback_data=f"do_join_{qid}_{c.id}")] for c in chars]
    kb.append([types.InlineKeyboardButton(text="🔙 Отмена", callback_data=f"view_q_{qid}")])
    await callback.message.edit_text("Кем записаться?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("do_join_"))
async def do_join(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    qid, cid = int(parts[2]), int(parts[3])
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    char = session.get(Character, cid)
    
    if not char: return await callback.answer("Ошибка чара.", show_alert=True)
    if session.query(QueueEntry).filter_by(queue_type_id=qid, user_id=user.id).first():
        return await callback.answer("Вы уже в очереди.", show_alert=True)
    
    limit = get_effective_limit_logic(user)
    current_count = session.query(QueueEntry).filter_by(user_id=user.id).count()
    if current_count >= limit: return await callback.answer(f"⛔ Лимит записей исчерпан! ({current_count}/{limit})", show_alert=True)
    
    session.add(QueueEntry(user_id=user.id, queue_type_id=qid, character_name=char.nickname))
    session.commit()
    
    main_char = session.query(Character).filter_by(user_id=user.id, is_main=True).first()
    main_nick = main_char.nickname if main_char else char.nickname
    asyncio.create_task(log_reward_to_sheet(queue_name=session.get(QueueType, qid).name, main_nick=main_nick, char_nick=char.nickname, manager_name=user.username, status="В очереди"))
    
    await callback.answer(f"Записан: {char.nickname}")
    await view_queue(callback)

@router.callback_query(F.data.startswith("leave_q_"))
async def leave_queue(callback: types.CallbackQuery):
    qid = int(callback.data.split("_")[2])
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    entry = session.query(QueueEntry).filter_by(queue_type_id=qid, user_id=user.id).first()
    
    if entry:
        main_char = session.query(Character).filter_by(user_id=user.id, is_main=True).first()
        main_nick = main_char.nickname if main_char else entry.character_name
        asyncio.create_task(log_reward_to_sheet(queue_name=entry.queue.name, main_nick=main_nick, char_nick=entry.character_name, manager_name=user.username, status="❌ Вышел"))
        session.delete(entry)
        session.commit()
        await callback.answer("Вы вышли.")
    else: await callback.answer("Уже вышли.", show_alert=True)
    await view_queue(callback)

@router.callback_query(F.data == "my_active_queues")
async def show_my_active_queues(callback: types.CallbackQuery):
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    entries = session.query(QueueEntry).filter_by(user_id=user.id).all()
    
    if not entries: 
        return await callback.message.edit_text("📭 <b>Нет активных записей.</b>", parse_mode="HTML", reply_markup=get_back_btn())
    
    text = "🏃 <b>Твои записи:</b>\n\n"
    kb = []
    
    for e in entries:
        text += f"🔹 <b>{e.queue.name}</b> — {e.character_name}\n"
        
        q_name = e.queue.name
        short_name = (q_name[:12] + '..') if len(q_name) > 12 else q_name
        
        row = [
            types.InlineKeyboardButton(text=f"🔄 {short_name}", callback_data=f"swap_start_{e.id}"),
            types.InlineKeyboardButton(text="❌ Выйти", callback_data=f"leave_q_{e.queue_type_id}")
        ]
        kb.append(row)
        
    # --- ДОБАВЛЯЕМ РАСШИФРОВКУ (LEGEND) ---
    text += "\n───────────────\n"
    text += "💡 <b>Подсказка:</b>\n"
    text += "🔄 — Сменить персонажа в этой очереди\n"
    text += "❌ — Покинуть эту очередь"
    # ---------------------------------------

    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("swap_start_"))
async def swap_start(callback: types.CallbackQuery):
    try: eid = int(callback.data.split("_")[2])
    except: return
    entry = session.get(QueueEntry, eid)
    if not entry: return await callback.answer("Не найдено.", show_alert=True)
    
    chars = session.query(Character).filter_by(user_id=entry.user_id).all()
    if len(chars) < 2: return await callback.answer("Нет других персонажей.", show_alert=True)
    
    kb = []
    for c in chars:
        if c.nickname == entry.character_name: continue
        kb.append([types.InlineKeyboardButton(text=f"🔄 На: {c.nickname}", callback_data=f"do_swap_{eid}_{c.id}")])
    kb.append([types.InlineKeyboardButton(text="🔙 Отмена", callback_data="my_active_queues")])
    await callback.message.edit_text(f"👇 Выберите замену для <b>{entry.character_name}</b>:", parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("do_swap_"))
async def do_swap_finish(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    eid, cid = int(parts[2]), int(parts[3])
    entry = session.get(QueueEntry, eid)
    new_char = session.get(Character, cid)
    
    if entry and new_char:
        old_nick = entry.character_name
        entry.character_name = new_char.nickname
        session.commit()
        
        user = session.get(User, entry.user_id)
        main_char = session.query(Character).filter_by(user_id=user.id, is_main=True).first()
        main_nick = main_char.nickname if main_char else new_char.nickname
        asyncio.create_task(log_reward_to_sheet(queue_name=entry.queue.name, main_nick=main_nick, char_nick=new_char.nickname, manager_name=user.username, status=f"🔄 Замена ({old_nick})"))
        
        await callback.answer(f"✅ {old_nick} -> {new_char.nickname}")
        await show_my_active_queues(callback)
    else: await show_my_active_queues(callback)

@router.callback_query(F.data == "menu_history")
async def my_history(callback: types.CallbackQuery):
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    hist = session.query(RewardHistory).filter_by(user_id=user.id).order_by(RewardHistory.timestamp.desc()).limit(10).all()
    text = "📜 <b>История наград:</b>\n" + ("<i>Пусто</i>" if not hist else "")
    for h in hist: text += f"🔹 {h.timestamp.strftime('%d.%m')} — {h.queue_name} ({h.character_name})\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_btn())

@router.callback_query(F.data == "menu_info")
async def info_queues(callback: types.CallbackQuery):
    queues = session.query(QueueType).filter_by(is_active=True).all()
    text = "ℹ️ <b>Справка:</b>\n\n"
    for q in queues: text += f"🔹 <b>{q.name}</b>\n{q.description}\n\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_btn())