from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import Character, Player, QueueEntry, Settings, User


def join_queue(session: Session, user_id: int, queue_id: int, char_id: int, is_auto: bool) -> Tuple[bool, str]:
    """
    Attempts to add a character to a queue.
    Returns: (success, message)
    """
    # 1. Validate inputs
    char = session.get(Character, char_id)
    if not char:
        return False, "Ошибка чара.", None

    # 2. Check if already in queue
    existing = session.query(QueueEntry).filter_by(queue_type_id=queue_id, user_id=user_id).first()
    if existing:
        return False, "Вы уже в очереди.", None

    # 3. Check Limits
    user = session.get(User, user_id)

    # Calculate effective limit
    limit = 1  # Default
    if user.personal_limit is not None:
        limit = user.personal_limit
    else:
        setting = session.query(Settings).filter_by(key="default_limit").first()
        if setting:
            limit = int(setting.value)

    current_count = session.query(QueueEntry).filter_by(user_id=user.id).count()
    if current_count >= limit:
        return False, f"⛔ Лимит записей исчерпан! ({current_count}/{limit})", None

    # 4. Add Entry
    entry = QueueEntry(user_id=user.id, queue_type_id=queue_id, character_name=char.nickname, auto_requeue=is_auto)
    session.add(entry)
    # Commit is left to the caller usually, but for a "service" method that does the whole action,
    # we might want to commit here or let the handler do it.
    # To keep it testable without side effects if possible, but we need ID for logging.
    # Let's flush or commit.
    session.commit()

    return True, f"Записан: {char.nickname} ({'Авто' if is_auto else '1 раз'})", entry


def leave_queue(session: Session, user_id: int, queue_id: int) -> Tuple[bool, str, Optional[QueueEntry]]:
    """
    Removes user from queue.
    Returns: (success, message, deleted_entry_copy)
    """
    entry = session.query(QueueEntry).filter_by(queue_type_id=queue_id, user_id=user_id).first()

    if entry:
        # We might need data for logging after deletion
        # Create a transient copy or just extract info needed
        # OR return the entry attached to session but marked corresponding?
        # Once deleted and committed, it's gone.

        # We'll return the object BEFORE commit if we didn't expire it?
        # Actually, let's just return the info needed.
        # But for test, we want to know it was deleted.

        session.delete(entry)
        session.commit()

        # Return a mock object or simple dict for logging usage?
        # For now, just bool/msg is enough for logic test. The handler needs info for logging.
        # Let's pass back the `entry` object, but know it's detached/deleted.
        return True, "Вы вышли.", entry
    else:
        return False, "Уже вышли.", None


def get_admin_queue_entries(session: Session, queue_id: int):
    """
    Returns filtered queue entries for admin reward distribution.
    Filters out characters that are explicitly NOT in guild (in_clan=0).
    """
    return (
        session.query(QueueEntry)
        .outerjoin(Player, func.lower(QueueEntry.character_name) == func.lower(Player.nickname))
        .filter(QueueEntry.queue_type_id == queue_id)
        .filter((Player.in_clan == 1) | (Player.in_clan.is_(None)))
        .all()
    )


def get_admin_queue_count(session: Session, queue_id: int) -> int:
    """
    Returns count of filtered queue entries for admin reward distribution.
    """
    return (
        session.query(QueueEntry)
        .outerjoin(Player, func.lower(QueueEntry.character_name) == func.lower(Player.nickname))
        .filter(QueueEntry.queue_type_id == queue_id)
        .filter((Player.in_clan == 1) | (Player.in_clan.is_(None)))
        .count()
    )
