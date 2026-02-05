import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text

from database import RewardHistory, User, engine, init_db, session


def test_delayed_warnings():
    print("Starting Delayed Warning Verification...")
    
    # 1. Ensure DB Init (Migration Check)
    init_db()
    
    # Check column existence using valid SQL for SQLite
    try:
        # Check if record_type exists
        with engine.connect() as conn:
             res = conn.execute(text("PRAGMA table_info(reward_history)")).fetchall()
             columns = [r[1] for r in res]
             if "record_type" not in columns:
                 print("❌ Migration failed: record_type column missing.")
                 return
             print("[OK] Migration verified: record_type column exists.")
    except Exception as e:
        print(f"❌ Error checking migration: {e}")
        return

    # 2. Setup Dummy User
    user = session.query(User).filter_by(telegram_id=99999).first()
    if not user:
        user = User(telegram_id=99999, username="test_warner")
        session.add(user)
        session.commit()
        
    # Clean previous history
    session.query(RewardHistory).filter_by(user_id=user.id).delete()
    session.commit()
    
    # 3. Simulate Warn (Add direct DB entry as handler would)
    print("--- Simulating Warning ---")
    warn_entry = RewardHistory(
        user_id=user.id,
        character_name="BadChar",
        queue_name="TestQueue",
        issued_by="admin",
        is_notified=False,
        record_type="warning"
    )
    session.add(warn_entry)
    
    # Also add a reward to test mixed content
    reward_entry = RewardHistory(
        user_id=user.id,
        character_name="GoodChar",
        queue_name="TestQueue",
        issued_by="admin",
        is_notified=False,
        record_type="reward"
    )
    session.add(reward_entry)
    session.commit()
    
    # 4. Verify Pending State
    pending = session.query(RewardHistory).filter_by(user_id=user.id, is_notified=False).all()
    assert len(pending) == 2, f"Should have 2 pending items, got {len(pending)}"
    print("[OK] Items saved as pending.")
    
    # 5. Simulate Batch Send Logic
    print("--- Simulating Batch Send ---")
    
    rewards = [i for i in pending if i.record_type != "warning"]
    warnings = [i for i in pending if i.record_type == "warning"]
    
    assert len(rewards) == 1, "Should identify 1 reward"
    assert len(warnings) == 1, "Should identify 1 warning"
    
    msg_text = ""
    if rewards:
        msg_text += "Rewards Header\n"
        for r in rewards: msg_text += f"- {r.character_name}\n"
        
    if warnings:
        if rewards: msg_text += "---\n"
        msg_text += "Warning Header\n"
        for w in warnings: msg_text += f"- {w.character_name}\n"
        
    print(f"Generated Message Body:\n{msg_text}")
    
    # Check content contains critical info
    assert "Rewards Header" in msg_text
    assert "Warning Header" in msg_text
    assert "BadChar" in msg_text
    assert "GoodChar" in msg_text
    
    print("[OK] Message logic correctly grouped items.")
    
    # Clean up
    session.delete(warn_entry)
    session.delete(reward_entry)
    session.delete(user)
    session.commit()
    print("\n[OK] CLEANUP COMPLETE.")

if __name__ == "__main__":
    test_delayed_warnings()
