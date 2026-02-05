import logging
from typing import Any, Dict, Optional

import aiosqlite

import web_database

async def join_queue(user_id: int, queue_id: int, char_name: Optional[str], auto_requeue: bool) -> Dict[str, Any]:
    """
    Add a user to a specific queue.
    """
    try:
        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            # Check for duplicate entry in same queue
            async with conn.execute("""
                SELECT id FROM queue_entries 
                WHERE user_id = ? AND queue_type_id = ?
            """, (user_id, queue_id)) as cursor:
                existing = await cursor.fetchone()
                if existing:
                    return {"status": "error", "message": "Вы уже записаны в эту очередь"}
            
            # Insert with auto_requeue flag
            await conn.execute("""
                INSERT INTO queue_entries (user_id, queue_type_id, character_name, auto_requeue)
                VALUES (?, ?, ?, ?)
            """, (user_id, queue_id, char_name, 1 if auto_requeue else 0))
            await conn.commit()
            
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Error in join_queue: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

async def leave_queue(entry_id: int) -> Dict[str, Any]:
    """
    Remove a user from a queue entry.
    """
    try:
        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            await conn.execute("DELETE FROM queue_entries WHERE id = ?", (entry_id,))
            await conn.commit()
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Error in leave_queue: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
