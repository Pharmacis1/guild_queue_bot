import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import Character, Event, PartyMember, Player, QueueEntry, User, \
    get_effective_limit_logic, get_msk_now, get_user_active_queues

session = None # Placeholder for legacy sync tests to patch


def get_start_of_week() -> int:
    """Возвращает timestamp (int) начала текущей недели (понедельник 00:00)."""
    now = datetime.datetime.now()
    start_of_week = now - datetime.timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start_of_week.timestamp())


async def is_character_in_guild(session: AsyncSession, nickname: str) -> bool:
    """
    Проверяет, состоит ли персонаж в гильдии.
    """
    result = await session.execute(
        select(Player).filter(func.lower(Player.nickname) == func.lower(nickname))
    )
    player = result.scalar_one_or_none()
    if not player:
        return True  # Нет в базе - считаем легальным (добавлен мастером)
    return player.in_clan == 1


async def get_user_weekly_valor_map(session: AsyncSession, user: User) -> Dict[str, int]:
    """Возвращает словарь {nickname: valor} для персонажей пользователя за текущую неделю."""
    char_map = {c.nickname: 0 for c in user.characters}
    if not char_map:
        return {}

    nicks = list(char_map.keys())

    # 2. Ищем role_id этих персонажей
    result = await session.execute(select(Player).filter(Player.nickname.in_(nicks)))
    players = result.scalars().all()
    if not players:
        return char_map

    player_map = {p.role_id: p.nickname for p in players}
    role_ids = list(player_map.keys())

    if not role_ids:
        return char_map

    # 3. Суммируем события за неделю с группировкой по role_id
    start_ts = get_start_of_week()
    stmt = (
        select(Event.role_id, func.sum(Event.value))
        .filter(Event.event_type == 1, Event.role_id.in_(role_ids), Event.timestamp >= start_ts)
        .group_by(Event.role_id)
    )
    result = await session.execute(stmt)
    events = result.all()

    # 4. Заполняем результат
    for rid, total in events:
        if rid in player_map:
            nick = player_map[rid]
            if nick in char_map:
                char_map[nick] = total or 0

    return char_map


async def get_queue_position(session: AsyncSession, entry: QueueEntry) -> int:
    """Возвращает позицию персонажа в очереди (1-based), исключая тех, кто не в ги."""
    stmt = (
        select(func.count(QueueEntry.id))
        .outerjoin(Player, func.lower(QueueEntry.character_name) == func.lower(Player.nickname))
        .filter(
            QueueEntry.queue_type_id == entry.queue_type_id,
            QueueEntry.id < entry.id,
            (Player.in_clan == 1) | (Player.in_clan.is_(None))
        )
    )
    result = await session.execute(stmt)
    position = result.scalar() or 0
    return position + 1


async def get_menu_text(session: AsyncSession, user: User, custom_title=None) -> Tuple[str, bool]:
    """
    Генерирует текст меню.
    """
    if not user.characters:
        return (
            "👋 <b>Привет!</b>\n\n"
            "Чтобы получить ресы с КХ, следуй простой инструкции:\n"
            "1️⃣ Зайди в <b>«👥 Мои персонажи»</b> и добавь своего основного персонажа и твинов (если есть).\n"
            "2️⃣ Нажми <b>«✍️ Записаться в очередь»</b>, выбери нужную очередь и нажми на ник своего персонажа.\n\n"
            "🤖 Бот пришлет уведомление, когда Мастер выдаст тебе награду.\n\n"
            "👇 <b>Выбери действие:</b>"
        ), False

    # --- СБОР СТАТИСТИКИ ---
    active_queues = await get_user_active_queues(session, user.id)
    current_count = len(active_queues)
    limit = await get_effective_limit_logic(session, user)
    available_slots = max(0, limit - current_count)

    # Считаем доблесть по персонажам
    valor_map = await get_user_weekly_valor_map(session, user)

    chars_display_list = []
    all_out_of_guild = True
    for char in user.characters:
        in_guild = await is_character_in_guild(session, char.nickname)
        if in_guild:
            all_out_of_guild = False
        
        val = valor_map.get(char.nickname, 0)
        suffix = " (не в ги)" if not in_guild else ""
        
        char_line = f"• <b>{char.nickname}</b>{suffix} ({val} добл.)"
        
        # Получаем информацию о КП
        result = await session.execute(
            select(Player).filter(func.lower(Player.nickname) == func.lower(char.nickname))
        )
        player = result.scalar_one_or_none()
        if player and player.role_id:
            # Need to load pm and its party
            stmt = (
                select(PartyMember)
                .filter_by(player_role_id=player.role_id)
                .options(selectinload(PartyMember.party))
            )
            result = await session.execute(stmt)
            pm = result.scalar_one_or_none()
            if pm:
                party = pm.party
                if party.name:
                    char_line += f"\n  КП: «{party.name}»"
                else:
                    # Find leader
                    stmt_leader = (
                        select(PartyMember)
                        .filter_by(party_id=party.id, is_leader=True)
                    )
                    result_leader = await session.execute(stmt_leader)
                    leader_pm = result_leader.scalar_one_or_none()
                    if leader_pm:
                        result_leader_player = await session.execute(
                            select(Player).filter_by(role_id=leader_pm.player_role_id)
                        )
                        leader_player = result_leader_player.scalar_one_or_none()
                        leader_nick = leader_player.nickname if leader_player else "Неизвестно"
                        char_line += f"\n  КП: {leader_nick}"
                    else:
                        char_line += f"\n  КП: Неизвестно"

        chars_display_list.append(char_line)

    chars_str = "\n".join(chars_display_list)

    if active_queues:
        q_list_lines = []
        for q in active_queues:
            # Re-fetch with join to get queue name
            result = await session.execute(
                select(QueueEntry).filter_by(id=q.id).options(selectinload(QueueEntry.queue))
            )
            full_q = result.scalar_one()
            pos = await get_queue_position(session, full_q)
            q_list_lines.append(f"- <b>{full_q.queue.name}</b> ({full_q.character_name}) — {pos}-й в очереди")
        queues_display = "\n".join(q_list_lines)
    else:
        queues_display = "<i>Нет активных записей</i>"

    header = custom_title if custom_title else "👋 <b>С возвращением!</b>"

    afk_info = ""
    if user.afk_start and user.afk_end:
        now = get_msk_now()
        if user.afk_end >= now:
            afk_info = f"🛌 <b>Режим AFK:</b> {user.afk_start.strftime('%d.%m')} - {user.afk_end.strftime('%d.%m')}\n\n"

    return (
        f"{header}\n\n"
        f"👤 <b>Твои персонажи:</b>\n{chars_str}\n\n"
        f"📋 <b>Твои очереди на КХ ресы:</b>\n{queues_display}\n\n"
        f"📊 <b>Лимит записей в очереди:</b> {current_count}/{limit} (доступно: {available_slots})\n\n"
        f"{afk_info}"
        f"👇 <b>Выбери действие:</b>"
    ), all_out_of_guild


async def get_user_main_role_id(session: AsyncSession, user: User) -> Optional[int]:
    """Возвращает role_id основного персонажа пользователя."""
    from database import Player
    
    # 1. Check if user has a character set as main in Character table
    stmt_c = select(Character).where(Character.user_id == user.id, Character.is_main == True)
    res_c = await session.execute(stmt_c)
    main_char = res_c.scalar_one_or_none()
    
    if main_char:
        # Get role_id for this nickname
        stmt_p = select(Player.role_id).where(func.lower(Player.nickname) == func.lower(main_char.nickname))
        res_p = await session.execute(stmt_p)
        role_id = res_p.scalar_one_or_none()
        if role_id: return role_id
    
    # 2. Fallback: find any player record linked to this user that is NOT an alt
    stmt_p2 = select(Player.role_id).where(Player.user_id == user.id, Player.is_alt == False)
    res_p2 = await session.execute(stmt_p2)
    role_id = res_p2.scalar_one_or_none()
    if role_id:
        return role_id
        
    # 3. Last fallback: first available player record
    stmt_p3 = select(Player.role_id).where(Player.user_id == user.id).limit(1)
    res_p3 = await session.execute(stmt_p3)
    return res_p3.scalar_one_or_none()


async def update_user_menu_button(user_tg_id: int, role_id: Optional[int]):
    """Обновляет кнопку меню в Телеграме для конкретного пользователя."""
    from aiogram.types import MenuButtonWebApp, WebAppInfo
    from loader import bot
    from typing import Optional
    import os
    
    site_url = os.getenv("SITE_URL")
    if not site_url: return
    url = site_url
    if role_id:
        url = f"{site_url}/player/{role_id}"
        
    try:
        await bot.set_chat_menu_button(
            chat_id=user_tg_id,
            menu_button=MenuButtonWebApp(
                text="📱 Мой Профиль",
                web_app=WebAppInfo(url=url)
            )
        )
    except Exception as e:
        import logging
        logging.error(f"Failed to set menu button for {user_tg_id}: {e}")
