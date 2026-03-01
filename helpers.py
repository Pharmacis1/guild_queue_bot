import datetime

from sqlalchemy import func

from database import Event, Player, QueueEntry, PartyMember, get_effective_limit_logic, get_msk_now, get_user_active_queues, session


def get_start_of_week():
    """Возвращает timestamp (int) начала текущей недели (понедельник 00:00)."""
    now = datetime.datetime.now()
    start_of_week = now - datetime.timedelta(days=now.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start_of_week.timestamp())


def is_character_in_guild(nickname: str) -> bool:
    """
    Проверяет, состоит ли персонаж в гильдии.
    - Если персонажа нет в таблице Player - считается 'в ги' (мог быть добавлен через мастера).
    - Если Player.in_clan == 1 - 'в ги'.
    - В остальных случаях - 'не в ги'.
    """
    player = session.query(Player).filter(func.lower(Player.nickname) == func.lower(nickname)).first()
    if not player:
        return True  # Нет в базе - считаем легальным (добавлен мастером)
    return player.in_clan == 1


def get_user_weekly_valor_map(user):
    """Возвращает словарь {nickname: valor} для персонажей пользователя за текущую неделю."""
    # 1. Собираем ники и мапим их структуру для быстрого доступа
    char_map = {c.nickname: 0 for c in user.characters}
    if not char_map:
        return {}

    nicks = list(char_map.keys())

    # 2. Ищем role_id этих персонажей
    players = session.query(Player).filter(Player.nickname.in_(nicks)).all()
    if not players:
        return char_map

    player_map = {p.role_id: p.nickname for p in players}
    role_ids = list(player_map.keys())

    if not role_ids:
        return char_map

    # 3. Суммируем события за неделю с группировкой по role_id
    start_ts = get_start_of_week()
    events = (
        session.query(Event.role_id, func.sum(Event.value))
        .filter(Event.event_type == 1, Event.role_id.in_(role_ids), Event.timestamp >= start_ts)
        .group_by(Event.role_id)
        .all()
    )

    # 4. Заполняем результат
    for rid, total in events:
        if rid in player_map:
            nick = player_map[rid]
            if nick in char_map:
                char_map[nick] = total or 0

    return char_map


def get_queue_position(entry):
    """Возвращает позицию персонажа в очереди (1-based), исключая тех, кто не в ги."""
    # Считаем количество записей в ТОЙ ЖЕ очереди, у которых id МЕНЬШЕ текущего
    # И при этом персонаж состоит в гильдии (или отсутствует в Player)
    position = (
        session.query(QueueEntry)
        .outerjoin(Player, func.lower(QueueEntry.character_name) == func.lower(Player.nickname))
        .filter(
            QueueEntry.queue_type_id == entry.queue_type_id,
            QueueEntry.id < entry.id,
            (Player.in_clan == 1) | (Player.in_clan.is_(None))
        )
        .count()
    )
    return position + 1


def get_menu_text(user, custom_title=None):
    """
    Генерирует текст меню.
    :param user: Объект пользователя
    :param custom_title: (Опционально) Заголовок сообщения. Если None — ставит приветствие.
    """
    # Если нет персонажей — всегда показываем инструкцию, заголовки тут не важны
    if not user.characters:
        return (
            "👋 <b>Привет!</b>\n\n"
            "Чтобы получить ресы с КХ, следуй простой инструкции:\n"
            "1️⃣ Зайди в <b>«👥 Мои персонажи»</b> и добавь своего основного персонажа и твинов (если есть).\n"
            "2️⃣ Нажми <b>«✍️ Записаться в очередь»</b>, выбери нужную очередь и нажми на ник своего персонажа.\n\n"
            "🤖 Бот пришлет уведомление, когда Мастер выдаст тебе награду.\n\n"
            "👇 <b>Выбери действие:</b>"
        )

    # --- СБОР СТАТИСТИКИ ---
    active_queues = get_user_active_queues(user.id)
    current_count = len(active_queues)
    limit = get_effective_limit_logic(user)
    available_slots = limit - current_count
    if available_slots < 0:
        available_slots = 0

    # Считаем доблесть по персонажам
    valor_map = get_user_weekly_valor_map(user)

    chars_display_list = []
    all_out_of_guild = True
    for char in user.characters:
        in_guild = is_character_in_guild(char.nickname)
        if in_guild:
            all_out_of_guild = False
        
        val = valor_map.get(char.nickname, 0)
        suffix = " (не в ги)" if not in_guild else ""
        
        char_line = f"• <b>{char.nickname}</b>{suffix} ({val} добл.)"
        
        # Получаем информацию о КП
        player = session.query(Player).filter(func.lower(Player.nickname) == func.lower(char.nickname)).first()
        if player and player.role_id:
            pm = session.query(PartyMember).filter_by(player_role_id=player.role_id).first()
            if pm:
                party = pm.party
                if party.name:
                    char_line += f"\n  КП: «{party.name}»"
                else:
                    leader_pm = session.query(PartyMember).filter_by(party_id=party.id, is_leader=True).first()
                    if leader_pm:
                        leader_player = session.query(Player).filter_by(role_id=leader_pm.player_role_id).first()
                        leader_nick = leader_player.nickname if leader_player else "Неизвестно"
                        char_line += f"\n  КП: {leader_nick}"
                    else:
                        char_line += f"\n  КП: Неизвестно"

        chars_display_list.append(char_line)

    chars_str = "\n".join(chars_display_list)

    if active_queues:
        q_list_lines = []
        for q in active_queues:
            pos = get_queue_position(q)
            q_list_lines.append(f"- <b>{q.queue.name}</b> ({q.character_name}) — {pos}-й в очереди")
        queues_display = "\n".join(q_list_lines)
    else:
        queues_display = "<i>Нет активных записей</i>"

    # --- ФОРМИРОВАНИЕ ЗАГОЛОВКА ---
    # Если заголовок передали — используем его, иначе — стандартное приветствие
    header = custom_title if custom_title else "👋 <b>С возвращением!</b>"

    afk_info = ""
    if user.afk_start and user.afk_end:
        # Check expiration
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
