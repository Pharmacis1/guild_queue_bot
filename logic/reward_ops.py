from typing import Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from database import QueueEntry, RewardHistory, User

async def issue_reward(session: AsyncSession, entry_id: int, master_username: str) -> Tuple[bool, str, Optional[RewardHistory]]:
    """
    Issues a reward to the user associated with the queue entry.
    Handles auto-requeue logic.
    Returns: (success, message, created_history_record)
    """
    from sqlalchemy.orm import selectinload
    stmt = select(QueueEntry).filter_by(id=entry_id).options(
        selectinload(QueueEntry.queue),
        selectinload(QueueEntry.user)
    )
    res = await session.execute(stmt)
    entry = res.scalar_one_or_none()
    
    if not entry:
        return False, "Уже выдано/удалено.", None

    qid = entry.queue_type_id
    q_name = entry.queue.name
    char_nick = entry.character_name

    # Create History Record (is_notified=False)
    history = RewardHistory(
        user_id=entry.user_id,
        character_name=char_nick,
        queue_name=q_name,
        issued_by=master_username,
        is_notified=False,
    )
    session.add(history)

    # Auto-Requeue Logic
    if entry.auto_requeue:
        # Calculate next position
        stmt = select(func.max(QueueEntry.position)).filter_by(queue_type_id=qid)
        result = await session.execute(stmt)
        max_pos = result.scalar() or 0
        new_entry = QueueEntry(
            user_id=entry.user_id, 
            queue_type_id=qid, 
            character_name=char_nick, 
            auto_requeue=True,
            position=max_pos + 1
        )
        session.add(new_entry)
        msg_suffix = "(Перезаписан)"
    else:
        msg_suffix = "(Ушел)"

    # Delete old entry
    await session.delete(entry)
    await session.commit()

    return True, f"✅ Выдано: {char_nick} {msg_suffix}", history


async def warn_user(session: AsyncSession, entry_id: int, master_username: str) -> Tuple[bool, str, Optional[RewardHistory]]:
    """
    Issues a warning to the user (delayed notification).
    """
    from sqlalchemy.orm import selectinload
    stmt = select(QueueEntry).filter_by(id=entry_id).options(
        selectinload(QueueEntry.queue),
        selectinload(QueueEntry.user)
    )
    res = await session.execute(stmt)
    entry = res.scalar_one_or_none()

    if not entry:
        return False, "Запись не найдена.", None

    user = await session.get(User, entry.user_id) if entry.user_id else None

    safe_uid = user.id if user else None

    history = RewardHistory(
        user_id=safe_uid,
        character_name=entry.character_name,
        queue_name=entry.queue.name,
        issued_by=master_username,
        is_notified=False,
        record_type="warning",
    )
    session.add(history)
    await session.commit()

    if user:
        return True, "⚠️ Предупреждение отложено (в список рассылки).", history
    else:
        return True, "⚠️ Записано (нет привязки к юзеру).", history
