import asyncio
from datetime import datetime, timedelta

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

# Импорты из корня проекта
from database import (
    DEFAULT_QUEUES,
    AFKHistory,
    Character,
    Player,
    QueueEntry,
    QueueType,
    RewardHistory,
    User,
    ensure_user,
    get_msk_now,
    get_setting,
    session,
)
from helpers import get_menu_text
from keyboards import (
    get_afk_end_kb,
    get_afk_menu,
    get_afk_start_kb,
    get_back_btn,
    get_main_menu,
    get_pending_menu,
    get_persistent_menu,
    get_unauthorized_menu,
)
from loader import bot
from logic.queue_ops import join_queue, leave_queue
from states import AFKState, Registration
from utils import check_google_sheet, log_reward_to_sheet

router = Router()


@router.message(Command("id"))
async def cmd_get_id(message: types.Message):
    text = f"ID этого чата: <code>{message.chat.id}</code>"
    if message.message_thread_id:
        text += f"\nID топика: <code>{message.message_thread_id}</code>"
    await message.reply(text, parse_mode="HTML")


@router.message(Command("start"), F.chat.type != "private")
async def group_start_stub(message: types.Message):
    await message.reply("Эта команда доступна только в личных сообщениях со мной 🕷")


# --- START ---
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user = ensure_user(message.from_user.id, message.from_user.username)
    if user.is_banned:
        return await message.answer("⛔ <b>Вы забанены.</b>", parse_mode="HTML")

    # Check for main character
    main_char = session.query(Character).filter_by(user_id=user.id, is_main=True).first()

    # Self-healing: If no main char found, but user HAS characters (e.g. main deleted), make one main.
    if not main_char:
        any_char = session.query(Character).filter_by(user_id=user.id).first()
        if any_char:
            any_char.is_main = True
            session.commit()
            main_char = any_char  # Recovered

    if not main_char:
        # Check for pending request
        if user.pending_request_nick:
            text = (
                f"🛡 <b>Заявка отправлена Мастеру.</b>\n\n"
                f"Вы подали заявку на привязку персонажа: <b>{user.pending_request_nick}</b>.\n"
                "Ожидайте подтверждения, либо вы можете исправить/отменить заявку ниже."
            )
            return await message.answer(
                text, parse_mode="HTML", reply_markup=get_pending_menu(user.pending_request_nick)
            )

        text = (
            "🛡 <b>Добро пожаловать в бота гильдии arahnius!</b>\n\n"
            "Для того, чтобы начать пользоваться ботом, нужно состоять в клане <b>arahnius</b> и пройти авторизацию.\n\n"
            "👇 Если вы вступили в клан, нажмите на кнопку ниже <b>«Добавить основу»</b> и введите никнейм персонажа (точный, как в игре), который состоит в гильдии. "
            "Бот проверит его наличие в составе."
        )
        return await message.answer(text, parse_mode="HTML", reply_markup=get_unauthorized_menu())

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


# ... (rest of simple handlers)


@router.callback_query(F.data == "cancel_request")
async def cancel_pending_request(callback: types.CallbackQuery, state: FSMContext):
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    cancelled_nick = user.pending_request_nick
    user.pending_request_nick = None
    session.commit()

    # Notify Masters about cancellation
    if cancelled_nick:
        masters = session.query(User).filter_by(is_master=True).all()
        user_desc = f"@{user.username}" if user.username else f"ID {user.telegram_id}"
        for m in masters:
            try:
                await bot.send_message(
                    m.telegram_id,
                    f"❌ <b>Пользователь отменил заявку!</b>\nИгрок: {user_desc}\nНик: {cancelled_nick}\n\n<i>Не нажимайте «Принять» на предыдущем сообщении.</i>",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    await callback.answer("Заявка отменена.")
    # Show welcome again
    await cmd_start(callback.message)  # Reuse start logic for simplicity


@router.callback_query(F.data == "back_to_main")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    if user.is_banned:
        return await callback.message.edit_text("⛔ Вы забанены.", parse_mode="HTML")

    text = get_menu_text(user)
    try:
        await callback.message.edit_text(text, reply_markup=get_main_menu(user), parse_mode="HTML")
    except Exception:
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
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")],
    ]

    # Генерируем текст с кастомным заголовком
    text = get_menu_text(user, custom_title="⚙️ <b>Управление персонажами:</b>")

    await callback.message.edit_text(
        text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML"
    )


@router.callback_query(F.data == "add_main")
async def add_main_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✍️ Введи никнейм **ОСНОВЫ**:", reply_markup=get_back_btn("menu_chars"), parse_mode="Markdown"
    )
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
        if not is_known:
            text = "⚠️ Этого ника нет в базе.\n🔐 Введите код верификации, чтобы отправить заявку Мастеру:"

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
        return await message.answer(
            f"⚠️ Ник <b>{nick}</b> уже занят другим пользователем.",
            parse_mode="HTML",
            reply_markup=get_back_btn("menu_chars"),
        )

    if taken and taken.user_id == user.id:
        taken.is_main = True
        session.commit()
    else:
        session.add(Character(user_id=user.id, nickname=nick, is_main=True))
        # Adopt orphaned entries
        orphans = session.query(QueueEntry).filter_by(character_name=nick, user_id=None).all()
        for o in orphans:
            o.user_id = user.id
        session.commit()

    await message.answer(
        f"✅ Основа сохранена: <b>{nick}</b>\n\nДобро пожаловать в клан! 🕷",
        parse_mode="HTML",
        reply_markup=get_main_menu(user),
    )

    # Auto-Invite: DISABLED
    # count = session.query(Character).filter_by(user_id=user.id).count()
    # if count == 1:
    #     chat_id = get_setting('clan_chat_id')
    #     if chat_id:
    #         try:
    #             link = await message.bot.create_chat_invite_link(chat_id, member_limit=1, name=f"For {user.username or user.telegram_id}")
    #             await message.answer(f"👋 <b>Ссылка на вступление в группу клана:</b>\n{link.invite_link}", parse_mode="HTML")
    #         except Exception as e:
    #             print(f"Error creating invite: {e}")
    await state.clear()


@router.callback_query(F.data == "add_alt")
async def add_alt_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✍️ Введи никнейм **ТВИНА**:", reply_markup=get_back_btn("menu_chars"), parse_mode="Markdown"
    )
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
            text = (
                "⚠️ Возможно, этот персонаж уже вступил в гильдию, но в базе его ещё нет, либо в никнейме есть опечатки\n"
                "🔐 Если этот персонаж есть в гильдии, и вы правильно ввели никнейм, введите код верификации (он указан в клан листе гильдии), чтобы отправить заявку Мастеру:"
            )

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
        return await message.answer(
            "⛔ Сначала добавь <b>Основу</b>.", parse_mode="HTML", reply_markup=get_back_btn("menu_chars")
        )

    if session.query(Character).filter_by(user_id=user.id, nickname=nick).first():
        return await message.answer("⚠️ Уже добавлен.", reply_markup=get_back_btn("menu_chars"))

    session.add(Character(user_id=user.id, nickname=nick, is_main=False))
    # Adopt orphans
    orphans = session.query(QueueEntry).filter_by(character_name=nick, user_id=None).all()
    for o in orphans:
        o.user_id = user.id

    session.commit()
    await message.answer(f"✅ Твин добавлен: <b>{nick}</b>", parse_mode="HTML", reply_markup=get_main_menu(user))
    await state.clear()


@router.message(Registration.waiting_for_code)
async def process_verification_code(message: types.Message, state: FSMContext):
    input_code = message.text.strip()
    correct_code = get_setting("verification_code")

    if correct_code and input_code.lower() != correct_code.lower():
        return await message.answer(
            "❌ Неверный код! Попробуйте еще раз или нажмите Назад.", reply_markup=get_back_btn("menu_chars")
        )

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
        await message.answer(
            "Ошибка состояния. Начни заново.",
            reply_markup=get_main_menu(ensure_user(message.from_user.id, message.from_user.username)),
        )
        await state.clear()


async def send_approval_request(message: types.Message, state: FSMContext, nick: str, action: str):
    # Find masters
    masters = session.query(User).filter_by(is_master=True).all()
    if not masters:
        await message.answer(
            "⚠️ Нет Мастеров в сети. Попробуй позже.",
            reply_markup=get_main_menu(ensure_user(message.from_user.id, message.from_user.username)),
        )
        await state.clear()
        return

    user = ensure_user(message.from_user.id, message.from_user.username)
    type_str = "ОСНОВА" if action == "main_input" else "ТВИН"
    user_link = f"<a href='tg://user?id={user.telegram_id}'>{user.username or 'Без ника'}</a>"

    text = "🛡 <b>Заявка на добавление:</b>\n"
    text += f"Игрок: {user_link}\n"
    text += f"Ник: <code>{nick}</code> ({type_str})\n"
    text += "⚠️ <i>Этого ника нет в базе. Требуется подтверждение.</i>"

    kb = [
        [types.InlineKeyboardButton(text="✅ Принять", callback_data=f"appr:ok:{user.id}:{action}:{nick}")],
        [types.InlineKeyboardButton(text="✏️ Исправить и принять", callback_data=f"appr:edit:{user.id}:{action}")],
        [types.InlineKeyboardButton(text="❌ Отказать", callback_data=f"appr:no:{user.id}")],
    ]

    count = 0
    for m in masters:
        try:
            # Save temp data in a temporary storage? logic is stateless in callback.
            # We pass data in callback_data.
            await message.bot.send_message(
                m.telegram_id, text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
            )
            count += 1
        except Exception:
            pass

    if count > 0:
        # Save pending state ONLY if it's a main char request (unauthorized user flow)
        if action == "main_input":
            user.pending_request_nick = nick
            session.commit()
            await message.answer(
                f"⏳ <b>Заявка на {nick} отправлена Мастеру.</b>\nОжидайте подтверждения.",
                parse_mode="HTML",
                reply_markup=get_pending_menu(nick),
            )
        else:
            await message.answer(
                "⏳ <b>Заявка отправлена Мастеру.</b>\nОжидайте подтверждения.",
                parse_mode="HTML",
                reply_markup=get_unauthorized_menu(),
            )
    else:
        await message.answer("⚠️ Не удалось связаться с Мастером.", reply_markup=get_unauthorized_menu())

    await state.clear()


@router.callback_query(F.data == "del_alt_menu")
async def del_alt_menu(callback: types.CallbackQuery):
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    alts = session.query(Character).filter_by(user_id=user.id, is_main=False).all()
    if not alts:
        return await callback.answer("Нет твинов.", show_alert=True)
    kb = [[types.InlineKeyboardButton(text=f"❌ {c.nickname}", callback_data=f"del_c_{c.id}")] for c in alts]
    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="menu_chars")])
    await callback.message.edit_text("Кого удалить?", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))


@router.callback_query(F.data.startswith("del_c_"))
async def del_char_action(callback: types.CallbackQuery):
    cid = int(callback.data.split("_")[2])
    char = session.get(Character, cid)
    if not char:
        return await callback.answer("Не найден.")

    user = ensure_user(callback.from_user.id, callback.from_user.username)
    entries = session.query(QueueEntry).filter_by(character_name=char.nickname).all()
    if entries:
        main_char = session.query(Character).filter_by(user_id=user.id, is_main=True).first()
        text = f"⚠️ Персонаж <b>{char.nickname}</b> записан в очередях ({len(entries)} шт.)!\n\n"
        kb = []
        if main_char:
            text += f"Я заменю его на основу: <b>{main_char.nickname}</b>."
            kb.append(
                [
                    types.InlineKeyboardButton(
                        text=f"✅ Заменить на {main_char.nickname} и удалить", callback_data=f"conf_del_{cid}_swap"
                    )
                ]
            )
        else:
            text += "Он исчезнет из всех очередей."
            kb.append([types.InlineKeyboardButton(text="🗑 Удалить отовсюду", callback_data=f"conf_del_{cid}_kill")])
        kb.append([types.InlineKeyboardButton(text="🔙 Отмена", callback_data="menu_chars")])
        await callback.message.edit_text(
            text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
        )
    else:
        nick = char.nickname
        session.delete(char)
        session.commit()
        await callback.answer(f"{nick} удален.")

        # Check for kick
        count = session.query(Character).filter_by(user_id=user.id).count()
        if count == 0:
            chat_id = get_setting("clan_chat_id")
            if chat_id:
                try:
                    await callback.bot.ban_chat_member(chat_id, user.telegram_id)
                    await callback.bot.unban_chat_member(chat_id, user.telegram_id)
                    await callback.message.answer(
                        "⚠️ Вы были исключены из группы клана, так как у вас не осталось активных персонажей."
                    )
                except Exception as e:
                    print(f"Kick error: {e}")

        await del_alt_menu(callback)


@router.callback_query(F.data.startswith("conf_del_"))
async def confirm_del_char_complex(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    cid, action = int(parts[2]), parts[3]
    char = session.get(Character, cid)
    if not char:
        return await callback.answer("Уже удален.")

    nick_to_del, user_id = char.nickname, char.user_id
    user = session.get(User, user_id)
    entries = session.query(QueueEntry).filter_by(character_name=nick_to_del).all()

    for e in entries:
        q_name = e.queue.name
        if action == "swap":
            main_char = session.query(Character).filter_by(user_id=user_id, is_main=True).first()
            if main_char:
                e.character_name = main_char.nickname
                asyncio.create_task(
                    log_reward_to_sheet(
                        queue_name=q_name,
                        main_nick=main_char.nickname,
                        char_nick=main_char.nickname,
                        manager_name=user.username,
                        status=f"♻️ Авто-замена ({nick_to_del})",
                    )
                )
            else:
                session.delete(e)
        elif action == "kill":
            session.delete(e)
            asyncio.create_task(
                log_reward_to_sheet(
                    queue_name=q_name,
                    main_nick=nick_to_del,
                    char_nick=nick_to_del,
                    manager_name=user.username,
                    status="❌ Ушел (удаление перса)",
                )
            )

    session.delete(char)
    session.commit()

    # Check for kick
    count = session.query(Character).filter_by(user_id=user_id).count()
    if count == 0:
        chat_id = get_setting("clan_chat_id")
        if chat_id:
            try:
                await callback.bot.ban_chat_member(chat_id, user.telegram_id)
                await callback.bot.unban_chat_member(chat_id, user.telegram_id)
                await callback.message.answer(
                    "⚠️ Вы были исключены из группы клана, так как у вас не осталось активных персонажей."
                )
            except Exception as e:
                print(f"Kick error (complex): {e}")

    await callback.message.edit_text(f"✅ {nick_to_del} удален.", reply_markup=get_back_btn("menu_chars"))


# --- ОЧЕРЕДИ ---


@router.callback_query(F.data == "menu_join")
async def join_menu(callback: types.CallbackQuery):
    # Получаем пользователя для генерации текста
    user = ensure_user(callback.from_user.id, callback.from_user.username)

    queues = session.query(QueueType).filter_by(is_active=True).all()

    # Sort queues based on DEFAULT_QUEUES order
    def get_sort_index(q):
        try:
            return DEFAULT_QUEUES.index(q.name)
        except ValueError:
            return 999

    # Explicitly filter out removed queues
    REMOVED_QUEUES = ["Камень доблести", "Метеориты", "Опыт в диск", "Проходки в УФ", "Камни бессмертных"]
    queues = [q for q in queues if q.name not in REMOVED_QUEUES]

    queues.sort(key=get_sort_index)
    kb = []

    for q in queues:
        count = session.query(QueueEntry).filter_by(queue_type_id=q.id).count()
        status = "🔒 ЗАКРЫТА" if q.is_locked else f"({count})"
        kb.append([types.InlineKeyboardButton(text=f"{q.name} {status}", callback_data=f"view_q_{q.id}")])

    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])

    # Генерируем текст с кастомным заголовком
    text = get_menu_text(user, custom_title="✍️ <b>Запись в очередь:</b>")

    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data.startswith("view_q_"))
async def view_queue(callback: types.CallbackQuery):
    qid = int(callback.data.split("_")[2])
    q = session.get(QueueType, qid)
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    entries = (
        session.query(QueueEntry)
        .outerjoin(Player, QueueEntry.character_name == Player.nickname)
        .filter(QueueEntry.queue_type_id == qid)
        .filter((Player.in_clan == 1) | (Player.in_clan.is_(None)))
        .all()
    )

    text = f"🛡 <b>Очередь: {q.name}</b>\n\n"
    text += "Условия для получения награды из очереди:\n"
    text += f"{q.description}\n\n"
    if not entries:
        text += "<i>Пока пусто.</i>"
    else:
        for i, e in enumerate(entries, 1):
            text += f"{i}. {e.character_name}\n"

    kb = []
    user_entry = session.query(QueueEntry).filter_by(queue_type_id=qid, user_id=user.id).first()
    if user_entry:
        kb.append([types.InlineKeyboardButton(text="🏃 Выйти из очереди", callback_data=f"leave_q_{qid}")])
    else:
        # Restriction for Цилинь
        if q.name == "Цилинь":
            text += "\n\n👇 <b>Запись в эту очередь доступна только в разовом режиме.</b>"
            kb.append([types.InlineKeyboardButton(text="1️⃣ Записаться (Разово)", callback_data=f"pre_join_{qid}_once")])
        else:
            # New buttons: Once / Auto
            text += "\n\n👇 <b>Выберите режим записи:</b>\n"
            text += "• <b>1️⃣ Разово</b> — после получения награды вы покинете очередь.\n"
            text += "• <b>🔄 Авто</b> — после получения награды бот <u>автоматически</u> запишет вас в конец этой же очереди."

            kb.append(
                [
                    types.InlineKeyboardButton(text="1️⃣ Разово", callback_data=f"pre_join_{qid}_once"),
                    types.InlineKeyboardButton(text="🔄 Авто", callback_data=f"pre_join_{qid}_auto"),
                ]
            )

    kb.append([types.InlineKeyboardButton(text="🔙 К списку", callback_data="menu_join")])
    try:
        await callback.message.edit_text(
            text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("pre_join_"))
async def pre_join(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    qid = int(parts[2])
    # Check for mode in callback data (pre_join_{qid}_{mode})
    mode = parts[3] if len(parts) > 3 else "once"

    q = session.get(QueueType, qid)
    if q.is_locked:
        return await callback.answer("⛔ Очередь закрыта Мастером!", show_alert=True)

    # Force single mode for restricted queue
    if q.name == "Цилинь" and mode == "auto":
        mode = "once"

    user = ensure_user(callback.from_user.id, callback.from_user.username)
    chars = session.query(Character).filter_by(user_id=user.id).all()
    if not chars:
        return await callback.answer("Нет персонажей!", show_alert=True)

    # Direct to join_final with selected mode
    kb = [
        [
            types.InlineKeyboardButton(
                text=f"{'👑' if c.is_main else '👤'} {c.nickname}", callback_data=f"join_final_{qid}_{c.id}_{mode}"
            )
        ]
        for c in chars
    ]
    kb.append([types.InlineKeyboardButton(text="🔙 Отмена", callback_data=f"view_q_{qid}")])

    mode_text = "🔄 АВТО" if mode == "auto" else "1️⃣ РАЗОВО"
    await callback.message.edit_text(
        f"Кем записаться? ({mode_text})", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data.startswith("join_final_"))
async def join_final(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    qid, cid, mode = int(parts[2]), int(parts[3]), parts[4]

    user = ensure_user(callback.from_user.id, callback.from_user.username)
    # char and logic checks moved to queue_ops

    # Logic Call
    is_auto = mode == "auto"
    success, msg, entry = join_queue(session, user.id, qid, cid, is_auto)

    if not success:
        return await callback.answer(msg, show_alert=True)

    # Logging (Sheet)
    # Re-fetch or use entry?
    # entry is attached to session if session is same.
    # Note: queue_ops commits, so entry might be expired but refetchable?
    # Actually if we committed, the ID is valid.

    if entry:
        main_char = session.query(Character).filter_by(user_id=user.id, is_main=True).first()
        main_nick = main_char.nickname if main_char else entry.character_name

        log_status = "В очереди (Авто)" if is_auto else "В очереди"
        # We need Queue Name. Relationships should work if session is open for them.
        # But allow for lazy load or refresh.
        q_name = entry.queue.name

        asyncio.create_task(
            log_reward_to_sheet(
                queue_name=q_name,
                main_nick=main_nick,
                char_nick=entry.character_name,
                manager_name=user.username,
                status=log_status,
            )
        )

    await callback.answer(msg)
    await view_queue(callback)


@router.callback_query(F.data.startswith("leave_q_"))
async def leave_queue_handler(callback: types.CallbackQuery):
    qid = int(callback.data.split("_")[2])
    user = ensure_user(callback.from_user.id, callback.from_user.username)

    success, msg, deleted_entry = leave_queue(session, user.id, qid)

    if success and deleted_entry:
        # Logging
        # deleted_entry is detached but has character_name field populated?
        # leave_queue returns the object. Attributes like character_name are string, so they persist.
        # But relationships (deleted_entry.queue) might fail if lazy loaded from closed session or deleted row?
        # In leave_queue we committed delete.
        # So we can't access .queue logic attribute easily on deleted object unless it was eager loaded?
        # But leave_queue impl: `start_q = entry.queue.name` BEFORE delete.
        # Wait, I didn't update leave_queue to attach that info to the return object properly?
        # I returned `entry`.
        # In `leave_queue`:
        # `start_q = entry.queue.name`
        # `session.delete(entry)`
        # `return True, ..., entry`
        # The `entry` object will have its columns, but relations might be gone.
        # The `queue` relation probably fails.
        # I should simply query Queue name by ID separately or assume it from `start_q` if I passed it.
        # Actually I prefer `leave_queue` logic to return the summary dict or modified object with needed info.

        # IMPROVEMENT: Let's fetch Queue Name explicitly here since we have QID.
        q_name = session.get(QueueType, qid).name

        main_char = session.query(Character).filter_by(user_id=user.id, is_main=True).first()
        # deleted_entry.character_name should still be available in RAM object?
        # Yes, usually simple column attributes remain on the instance.

        main_nick = main_char.nickname if main_char else deleted_entry.character_name
        asyncio.create_task(
            log_reward_to_sheet(
                queue_name=q_name,
                main_nick=main_nick,
                char_nick=deleted_entry.character_name,
                manager_name=user.username,
                status="❌ Вышел",
            )
        )

        await callback.answer(msg)
    else:
        await callback.answer(msg, show_alert=True)

    await view_queue(callback)


@router.callback_query(F.data == "my_active_queues")
async def show_my_active_queues(callback: types.CallbackQuery):
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    entries = session.query(QueueEntry).filter_by(user_id=user.id).all()

    if not entries:
        return await callback.message.edit_text(
            "📭 <b>Нет активных записей.</b>", parse_mode="HTML", reply_markup=get_back_btn()
        )

    text = "🏃 <b>Твои записи:</b>\n\n"
    kb = []

    for e in entries:
        mode_icon = "♾" if e.auto_requeue else "1️⃣"
        text += f"🔹 <b>{e.queue.name}</b> — {e.character_name} ({mode_icon})\n"

        q_name = e.queue.name
        short_name = (q_name[:10] + "..") if len(q_name) > 10 else q_name

        row = [types.InlineKeyboardButton(text=f"🔄 {short_name}", callback_data=f"swap_start_{e.id}")]

        # Toggle button (Skip for Цилинь or other restricted if any)
        if e.queue.name != "Цилинь":
            row.append(types.InlineKeyboardButton(text=f"🔀 {mode_icon}", callback_data=f"toggle_mode_{e.id}"))

        row.append(types.InlineKeyboardButton(text="❌ Выйти", callback_data=f"leave_q_{e.queue_type_id}"))
        kb.append(row)

    # --- ДОБАВЛЯЕМ РАСШИФРОВКУ (LEGEND) ---
    text += "\n───────────────\n"
    text += "💡 <b>Подсказка:</b>\n"
    text += "🔄 — Сменить персонажа в этой очереди\n"
    text += "🔀 — Сменить режим (1️⃣ Разово / ♾ Авто)\n"
    text += "❌ — Покинуть эту очередь"
    # ---------------------------------------

    kb.append([types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])

    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb)
    )


@router.callback_query(F.data.startswith("toggle_mode_"))
async def toggle_mode_handler(callback: types.CallbackQuery):
    try:
        eid = int(callback.data.split("_")[2])
    except Exception:
        return
    entry = session.get(QueueEntry, eid)
    if not entry:
        return await callback.answer("Запись не найдена.", show_alert=True)

    if entry.queue.name == "Цилинь":
        return await callback.answer("Для этой очереди доступна только разовая запись.", show_alert=True)

    entry.auto_requeue = not entry.auto_requeue
    session.commit()

    status = "♾ Авто-запись" if entry.auto_requeue else "1️⃣ Разовая запись"
    await callback.answer(f"Режим изменен: {status}")
    await show_my_active_queues(callback)


@router.callback_query(F.data.startswith("swap_start_"))
async def swap_start(callback: types.CallbackQuery):
    try:
        eid = int(callback.data.split("_")[2])
    except Exception:
        return
    entry = session.get(QueueEntry, eid)
    if not entry:
        return await callback.answer("Не найдено.", show_alert=True)

    chars = session.query(Character).filter_by(user_id=entry.user_id).all()
    if len(chars) < 2:
        return await callback.answer("Нет других персонажей.", show_alert=True)

    kb = []
    for c in chars:
        if c.nickname == entry.character_name:
            continue
        kb.append([types.InlineKeyboardButton(text=f"🔄 На: {c.nickname}", callback_data=f"do_swap_{eid}_{c.id}")])
    kb.append([types.InlineKeyboardButton(text="🔙 Отмена", callback_data="my_active_queues")])
    await callback.message.edit_text(
        f"👇 Выберите замену для <b>{entry.character_name}</b>:",
        parse_mode="HTML",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb),
    )


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
        asyncio.create_task(
            log_reward_to_sheet(
                queue_name=entry.queue.name,
                main_nick=main_nick,
                char_nick=new_char.nickname,
                manager_name=user.username,
                status=f"🔄 Замена ({old_nick})",
            )
        )

        await callback.answer(f"✅ {old_nick} -> {new_char.nickname}")
        await show_my_active_queues(callback)
    else:
        await show_my_active_queues(callback)


@router.callback_query(F.data == "menu_history")
async def my_history(callback: types.CallbackQuery):
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    hist = (
        session.query(RewardHistory).filter_by(user_id=user.id).order_by(RewardHistory.timestamp.desc()).limit(10).all()
    )
    text = "📜 <b>История наград:</b>\n" + ("<i>Пусто</i>" if not hist else "")
    for h in hist:
        text += f"🔹 {h.timestamp.strftime('%d.%m')} — {h.queue_name} ({h.character_name})\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_btn())


@router.callback_query(F.data == "menu_info")
async def info_queues(callback: types.CallbackQuery):
    queues = session.query(QueueType).filter_by(is_active=True).all()

    # Sort queues
    def get_q_index(q):
        try:
            return DEFAULT_QUEUES.index(q.name)
        except ValueError:
            return 999

    # Explicitly filter out removed queues
    REMOVED_QUEUES = ["Камень доблести", "Метеориты", "Опыт в диск", "Проходки в УФ", "Камни бессмертных"]
    queues = [q for q in queues if q.name not in REMOVED_QUEUES]

    queues.sort(key=get_q_index)
    text = "ℹ️ <b>Справка</b>\n\nВыдаются от 120 доблести:\n- Камень доблести\n- Метеориты\n- Опыт в диск\n- Проходки в УФ\n- Камни бессмертных\n\nДля выдачи в очередь на эти ресурсы вставать не требуется.\n\n<b>Условия для получения награды из очередей на редкие ресурсы:</b>\n\n"
    for q in queues:
        text += f"🔹 <b>{q.name}</b>\n{q.description}\n\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_back_btn())


# --- AFK MENU ---


@router.callback_query(F.data == "menu_afk")
async def afk_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user = ensure_user(callback.from_user.id, callback.from_user.username)

    text = "🛌 <b>Режим AFK</b>\n\n"
    if user.afk_start and user.afk_end:
        s = user.afk_start.strftime("%d.%m.%Y")
        e = user.afk_end.strftime("%d.%m.%Y")
        
        now = get_msk_now()
        if user.afk_end >= now:
            text += f"✅ <b>Включен:</b>\nC {s} по {e}\n\n<i>В этот период на вас не будет распределяться награда из очередей.</i>"
        else:
            text += f"❌ <b>Истек:</b>\nC {s} по {e}\n\n<i>Срок действия режима AFK закончился. Вы можете задать новый период или очистить историю.</i>"
    else:
        text += "❌ <b>Выключен</b>\n\n<i>Включите этот режим, если планируете отсутствовать в игре длительное время (отпуск, командировка и т.д.).</i>"

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_afk_menu(user))


@router.callback_query(F.data == "afk_clear")
async def afk_clear(callback: types.CallbackQuery):
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    user.afk_start = None
    user.afk_end = None
    session.commit()
    await callback.answer("Режим AFK отключен.")
    await afk_menu(callback, None)  # Passing None as state is safe here or we can just ignore it if we don't use it


@router.callback_query(F.data == "afk_set")
async def afk_set_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📅 <b>Дата НАЧАЛА отсутствия:</b>\n\n"
        "Выберите вариант или напишите дату вручную в формате <code>ДД.ММ</code> (например, 25.01).",
        parse_mode="HTML",
        reply_markup=get_afk_start_kb(),
    )
    await state.set_state(AFKState.waiting_for_start)


# Helper for date parsing
def parse_date_input(text):
    text = text.strip()
    now = get_msk_now()

    # Try DD.MM
    try:
        d_str = text + f".{now.year}"
        dt = datetime.strptime(d_str, "%d.%m.%Y")

        # If date is in the past (e.g. user typed 01.01 but it's now 26.01), maybe they meant next year?
        # Or maybe they just made a mistake. Let's assume current year.
    except Exception:
        dt = None
        # But if it's December and they type 01.01, they mean next year.
        if dt.month < now.month:
            dt = dt.replace(year=now.year + 1)

        return dt
    except Exception:
        return None


@router.callback_query(AFKState.waiting_for_start, F.data.startswith("afk_date_"))
async def afk_start_quick(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[2]
    now = get_msk_now()

    if action == "today":
        dt = now
    elif action == "tomorrow":
        dt = now + timedelta(days=1)

    await state.update_data(start_date=dt)
    await ask_afk_end(callback.message, state)


@router.message(AFKState.waiting_for_start)
async def afk_start_manual(message: types.Message, state: FSMContext):
    dt = parse_date_input(message.text)
    if not dt:
        return await message.answer(
            "⚠️ Неверный формат даты. Используйте <code>ДД.ММ</code> (например 25.01)",
            parse_mode="HTML",
            reply_markup=get_afk_start_kb(),
        )

    await state.update_data(start_date=dt)
    await ask_afk_end(message, state)


async def ask_afk_end(message: types.Message, state: FSMContext):
    # This might be called from callback (message is accessible) or message
    msg = message if isinstance(message, types.Message) else message.message

    # If it was callback, we might need to edit. If message, answer.
    # For simplicity, let's always answer fresh message or edit if possible?
    # Mixing is tricky. Let's just use msg.answer if it was a message, or edit if callback.

    func = msg.edit_text if isinstance(message, types.CallbackQuery) else msg.answer

    await func(
        "🏁 <b>Дата ОКОНЧАНИЯ отсутствия:</b>\n\n"
        "Выберите длительность или напишите дату окончания вручную (<code>ДД.ММ</code>).",
        parse_mode="HTML",
        reply_markup=get_afk_end_kb(),
    )
    await state.set_state(AFKState.waiting_for_end)


@router.callback_query(AFKState.waiting_for_end, F.data.startswith("afk_dur_"))
async def afk_end_quick(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    start_dt = data.get("start_date")
    action = callback.data.split("_")[2]

    if action == "month":
        # End of current month of start_date?
        # Or end of current real month?
        # Let's assume end of current real month.
        import calendar

        now = start_dt
        last_day = calendar.monthrange(now.year, now.month)[1]
        end_dt = now.replace(day=last_day)
    else:
        days = int(action)
        end_dt = start_dt + timedelta(days=days)

    await finish_afk_setup(callback, state, start_dt, end_dt)


@router.message(AFKState.waiting_for_end)
async def afk_end_manual(message: types.Message, state: FSMContext):
    data = await state.get_data()
    start_dt = data.get("start_date")

    end_dt = parse_date_input(message.text)
    if not end_dt:
        return await message.answer(
            "⚠️ Неверный формат даты. Используйте <code>ДД.ММ</code>", parse_mode="HTML", reply_markup=get_afk_end_kb()
        )

    if end_dt < start_dt:
        return await message.answer("⚠️ Дата окончания не может быть раньше начала!", reply_markup=get_afk_end_kb())

    # Mock callback for consistency in finish function, or refactor
    # We can't easily mock callback. Let's make finish_afk_setup accept message too.
    user = ensure_user(message.from_user.id, message.from_user.username)
    user.afk_start = start_dt
    user.afk_end = end_dt

    # History
    session.add(AFKHistory(user_id=user.id, start_date=start_dt, end_date=end_dt))
    session.commit()

    await message.answer(
        f"✅ <b>Режим AFK установлен!</b>\n\n📅 {start_dt.strftime('%d.%m')} — {end_dt.strftime('%d.%m')}",
        parse_mode="HTML",
        reply_markup=get_afk_menu(user),
    )
    await state.clear()


async def finish_afk_setup(callback: types.CallbackQuery, state: FSMContext, start_dt, end_dt):
    user = ensure_user(callback.from_user.id, callback.from_user.username)
    user.afk_start = start_dt
    user.afk_end = end_dt

    # History
    session.add(AFKHistory(user_id=user.id, start_date=start_dt, end_date=end_dt))
    session.commit()

    await callback.message.edit_text(
        f"✅ <b>Режим AFK установлен!</b>\n\n📅 {start_dt.strftime('%d.%m')} — {end_dt.strftime('%d.%m')}",
        parse_mode="HTML",
        reply_markup=get_afk_menu(user),
    )
    await state.clear()
