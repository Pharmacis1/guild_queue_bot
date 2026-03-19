from typing import Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import Character, Player, QueueEntry, Settings, User


async def join_queue(session: AsyncSession, user_id: int, queue_id: int, char_id: int, is_auto: bool) -> Tuple[bool, str, Optional[QueueEntry]]:
    """
    Attempts to add a character to a queue.
    Returns: (success, message, entry)
    """
    # 1. Validate inputs
    char = await session.get(Character, char_id)
    if not char:
        return False, "Ошибка чара.", None

    # 2. Check if already in queue
    result = await session.execute(select(QueueEntry).filter_by(queue_type_id=queue_id, user_id=user_id))
    existing = result.scalar_one_or_none()
    if existing:
        return False, "Вы уже в очереди.", None

    # 3. Check Limits
    user = await session.get(User, user_id)

    # Calculate effective limit
    limit = 1  # Default
    if user.personal_limit is not None:
        limit = user.personal_limit
    else:
        result = await session.execute(select(Settings).filter_by(key="default_limit"))
        setting = result.scalar_one_or_none()
        if setting:
            limit = int(setting.value)

    result = await session.execute(select(func.count(QueueEntry.id)).filter_by(user_id=user.id))
    current_count = result.scalar()
    if current_count >= limit:
        return False, f"⛔ Лимит записей исчерпан! ({current_count}/{limit})", None

    # 4. Get max position
    max_pos_stmt = select(func.max(QueueEntry.position)).filter_by(queue_type_id=queue_id)
    max_pos_res = await session.execute(max_pos_stmt)
    max_pos = max_pos_res.scalar() or 0

    # 5. Add Entry
    entry = QueueEntry(
        user_id=user.id, 
        queue_type_id=queue_id, 
        character_name=char.nickname, 
        auto_requeue=is_auto,
        position=max_pos + 1
    )
    session.add(entry)
    await session.commit()

    return True, f"Записан: {char.nickname} ({'Авто' if is_auto else '1 раз'})", entry


async def leave_queue(session: AsyncSession, user_id: int, queue_id: int) -> Tuple[bool, str, Optional[QueueEntry]]:
    """
    Removes user from queue.
    Returns: (success, message, deleted_entry_copy)
    """
    result = await session.execute(select(QueueEntry).filter_by(queue_type_id=queue_id, user_id=user_id))
    entry = result.scalar_one_or_none()

    if entry:
        await session.delete(entry)
        await session.commit()
        return True, "Вы вышли.", entry
    else:
        return False, "Уже вышли.", None


async def get_admin_queue_entries(session: AsyncSession, queue_id: int):
    """
    Returns filtered queue entries for admin reward distribution.
    Filters out characters that are explicitly NOT in guild (in_clan=0).
    """
    from sqlalchemy.orm import selectinload
    stmt = (
        select(QueueEntry)
        .options(selectinload(QueueEntry.user))
        .outerjoin(Player, func.lower(QueueEntry.character_name) == func.lower(Player.nickname))
        .filter(QueueEntry.queue_type_id == queue_id)
        .filter((Player.in_clan == 1) | (Player.in_clan.is_(None)))
        .order_by(QueueEntry.position.asc(), QueueEntry.id.asc())
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_admin_queue_count(session: AsyncSession, queue_id: int) -> int:
    """
    Returns count of filtered queue entries for admin reward distribution.
    """
    stmt = (
        select(func.count(QueueEntry.id))
        .outerjoin(Player, func.lower(QueueEntry.character_name) == func.lower(Player.nickname))
        .filter(QueueEntry.queue_type_id == queue_id)
        .filter((Player.in_clan == 1) | (Player.in_clan.is_(None)))
    )
    result = await session.execute(stmt)
    return result.scalar() or 0
