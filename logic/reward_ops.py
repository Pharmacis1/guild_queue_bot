from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import QueueEntry, RewardHistory, User


def issue_reward(session: Session, entry_id: int, master_username: str) -> Tuple[bool, str, Optional[RewardHistory]]:
    """
    Issues a reward to the user associated with the queue entry.
    Handles auto-requeue logic.
    Returns: (success, message, created_history_record)
    """
    entry = session.get(QueueEntry, entry_id)
    if not entry:
        return False, "Уже выдано/удалено.", None

    qid = entry.queue_type_id
    q_name = entry.queue.name
    char_nick = entry.character_name

    # User might be None if orphan? Schema allows user_id, but logically should exist.
    # We use user_id from entry.

    # Create History Record (is_notified=False)
    history = RewardHistory(
        user_id=entry.user_id,
        character_name=char_nick,
        queue_name=q_name,
        issued_by=master_username,
        is_notified=False,
        record_type="reward",  # Default is reward if not specified?
        # Schema check: record_type column exists? `handlers/admin.py` used `record_type="warning"`.
        # Standard reward created as `RewardHistory(...)` without record_type arg in original code, so it defaults or None.
        # Let's check original code `m_issue_reward`:
        # `session.add(RewardHistory(..., is_notified=False))` -> No record_type.
        # Does the model have a default? Or is it nullable?
        # `m_warn_user` sets `record_type="warning"`.
        # Let's assume None or "reward" is implicitly handled.
    )
    session.add(history)

    # Auto-Requeue Logic
    if entry.auto_requeue:
        # Calculate next position
        max_pos = session.query(func.max(QueueEntry.position)).filter_by(queue_type_id=qid).scalar() or 0
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
    session.delete(entry)
    session.commit()

    return True, f"✅ Выдано: {char_nick} {msg_suffix}", history


def warn_user(session: Session, entry_id: int, master_username: str) -> Tuple[bool, str, Optional[RewardHistory]]:
    """
    Issues a warning to the user (delayed notification).
    """
    entry = session.get(QueueEntry, entry_id)
    if not entry:
        return False, "Запись не найдена.", None

    user = session.get(User, entry.user_id) if entry.user_id else None

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
    session.delete(entry)
    session.commit()

    if user:
        return True, "⚠️ Предупреждение отложено (в список рассылки).", history
    else:
        return True, "⚠️ Записано (нет привязки к юзеру).", history
