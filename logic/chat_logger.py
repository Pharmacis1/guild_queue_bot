from datetime import datetime, timedelta
from database import session, MessageLog, SummaryState, get_msk_now

def log_message(chat_id, thread_id, user_id, user_name, text):
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
        session.commit()
    except Exception as e:
        print(f"Error logging message: {e}")
        session.rollback()

def get_new_messages(chat_id, thread_id, limit=50):
    """
    Retrieves messages for a specific chat/thread that haven't been summarized yet.
    """
    # 1. Get last summary time
    state = session.query(SummaryState).filter_by(chat_id=chat_id, thread_id=thread_id).first()
    last_time = state.last_summary_time if state else None
    
    query = session.query(MessageLog).filter(
        MessageLog.chat_id == chat_id,
        MessageLog.thread_id == thread_id
    )
    
    if last_time:
        query = query.filter(MessageLog.timestamp > last_time)
    else:
        # If no previous summary, maybe limit to last 24h or last N messages?
        # User implies "messages I haven't seen". If never seen, show recent history.
        # But if we just started logging, history is empty.
        # If we have history but no SummaryState, it means first summary.
        # Summary shouldn't be infinite.
        # Let's limit to last 24 hours if no state.
        yesterday = get_msk_now() - timedelta(hours=24)
        query = query.filter(MessageLog.timestamp > yesterday)

    # Order by timestamp ASC (oldest first)
    msgs = query.order_by(MessageLog.timestamp.asc()).limit(limit).all()
    
    return msgs

def mark_summary_done(chat_id, thread_id):
    """
    Updates the cursor (last_summary_time) to the current time.
    """
    now = get_msk_now()
    
    state = session.query(SummaryState).filter_by(chat_id=chat_id, thread_id=thread_id).first()
    if not state:
        state = SummaryState(chat_id=chat_id, thread_id=thread_id)
        session.add(state)
    
    state.last_summary_time = now
    session.commit()
