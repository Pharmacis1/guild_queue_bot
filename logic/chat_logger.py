from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from database import MessageLog, SummaryState, get_msk_now

async def log_message(session: AsyncSession, chat_id, thread_id, user_id, user_name, text):
    """
    Logs a message to the database.
    """
    try:
        # Prevent logging excessively long messages or commands (handled in router usually, but here too)
        if text and len(text) > 4000:
            text = text[:4000] + "..."
            
        msg = MessageLog(
            chat_id=chat_id,
            thread_id=thread_id,
            user_id=user_id,
            user_name=user_name,
            text=text,
            timestamp=get_msk_now()
        )
        session.add(msg)
        await session.commit()
    except Exception as e:
        print(f"Error logging message: {e}")
        await session.rollback()

async def get_new_messages(session: AsyncSession, chat_id, thread_id, limit=50):
    """
    Retrieves messages for a specific chat/thread that haven't been summarized yet.
    """
    # 1. Get last summary time
    stmt_state = select(SummaryState).filter_by(chat_id=chat_id, thread_id=thread_id)
    result_state = await session.execute(stmt_state)
    state = result_state.scalar_one_or_none()
    last_time = state.last_summary_time if state else None
    
    stmt = select(MessageLog).filter(
        MessageLog.chat_id == chat_id,
        MessageLog.thread_id == thread_id
    )
    
    if last_time:
        stmt = stmt.filter(MessageLog.timestamp > last_time)
    else:
        # If no previous summary, limit to last 24 hours if no state.
        yesterday = get_msk_now() - timedelta(hours=24)
        stmt = stmt.filter(MessageLog.timestamp > yesterday)

    # Order by timestamp ASC (oldest first)
    stmt = stmt.order_by(MessageLog.timestamp.asc()).limit(limit)
    result = await session.execute(stmt)
    msgs = result.scalars().all()
    
    return msgs

async def mark_summary_done(session: AsyncSession, chat_id, thread_id):
    """
    Updates the cursor (last_summary_time) to the current time.
    """
    now = get_msk_now()
    
    stmt = select(SummaryState).filter_by(chat_id=chat_id, thread_id=thread_id)
    result = await session.execute(stmt)
    state = result.scalar_one_or_none()
    if not state:
        state = SummaryState(chat_id=chat_id, thread_id=thread_id)
        session.add(state)
    
    state.last_summary_time = now
    await session.commit()
