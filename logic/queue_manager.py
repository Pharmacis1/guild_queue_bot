import logging
from typing import Any, Dict, Optional

from sqlalchemy import select, func
from database import AsyncSessionLocal, QueueEntry


async def join_queue(user_id: int, queue_id: int, char_name: Optional[str], auto_requeue: bool) -> Dict[str, Any]:
    """
    Add a user to a specific queue.
    """
    try:
        async with AsyncSessionLocal() as session:
            # Check for duplicate entry in same queue
            stmt = select(QueueEntry).filter_by(user_id=user_id, queue_type_id=queue_id)
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                return {"status": "error", "message": "Вы уже записаны в эту очередь"}

            # Get max position
            max_pos_stmt = select(func.max(QueueEntry.position)).filter_by(queue_type_id=queue_id)
            max_pos_res = await session.execute(max_pos_stmt)
            max_pos = max_pos_res.scalar() or 0

            # Insert with auto_requeue flag
            entry = QueueEntry(
                user_id=user_id,
                queue_type_id=queue_id,
                character_name=char_name,
                auto_requeue=auto_requeue,
                position=max_pos + 1
            )
            session.add(entry)
            await session.commit()

        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Error in join_queue: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def leave_queue(entry_id: int) -> Dict[str, Any]:
    """
    Remove a user from a queue entry.
    """
    try:
        async with AsyncSessionLocal() as session:
            entry = await session.get(QueueEntry, entry_id)
            if entry:
                await session.delete(entry)
                await session.commit()
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Error in leave_queue: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
