import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


from database import Character, QueueEntry, QueueType, RewardHistory, User, init_db, session


def test_features():
    print("Starting Logic Verification...")
    
    # Setup
    with session.no_autoflush: # Prevent premature flushing
        # Create Dummy Data
        user = session.query(User).filter_by(telegram_id=12345).first()
        if not user:
            user = User(telegram_id=12345, username="test_user")
            session.add(user)
        
        char = session.query(Character).filter_by(nickname="TestChar").first()
        if not char:
            char = Character(user_id=user.id, nickname="TestChar", is_main=True)
            session.add(char)
            
        q = session.query(QueueType).filter_by(name="TestQueue").first()
        if not q:
            q = QueueType(name="TestQueue")
            session.add(q)
        
        session.commit()
        
        print("\n--- 1. Testing Signup (Auto-Requeue) ---")
        # Simulate Signup with Auto-Requeue
        entry = QueueEntry(user_id=user.id, queue_type_id=q.id, character_name="TestChar", auto_requeue=True)
        session.add(entry)
        session.commit()
        
        e_check = session.query(QueueEntry).filter_by(user_id=user.id, queue_type_id=q.id).first()
        assert e_check, "Entry should exist"
        assert e_check.auto_requeue == True, "Auto-requeue flag should be True"
        print("[OK] Signup + Auto-requeue flag saved.")

        print("\n--- 2. Testing Reward Issuance ---")
        # Simulate Reward Issue (Admin Logic)
        q_name = q.name
        char_nick = e_check.character_name
        
        # Add History (Notified=False)
        rh = RewardHistory(user_id=user.id, character_name=char_nick, queue_name=q_name, issued_by="admin", is_notified=False)
        session.add(rh)
        
        # Auto-Requeue Logic
        if e_check.auto_requeue:
            session.add(QueueEntry(user_id=user.id, queue_type_id=q.id, character_name=char_nick, auto_requeue=True))
            
        # Delete old
        session.delete(e_check)
        session.commit()
        
        # Check
        # 1. History exists and is_notified=False
        h_check = session.query(RewardHistory).filter_by(user_id=user.id, is_notified=False).first()
        assert h_check, "RewardHistory should exist"
        assert h_check.is_notified == False, "is_notified should be False"
        print("[OK] Reward History recorded (delayed).")
        
        # 2. User Requeued
        q_new = session.query(QueueEntry).filter_by(user_id=user.id, queue_type_id=q.id).first()
        assert q_new, "User should be requeued"
        assert q_new.id != e_check.id, "Should be a new entry ID"
        print("[OK] User automatically requeued.")

        print("\n--- 3. Testing Batch Notification Logic ---")
        # Simulate Batch Send
        pending = session.query(RewardHistory).filter_by(is_notified=False).all()
        assert len(pending) > 0, "Should be pending items"
        
        for p in pending:
            p.is_notified = True # Simulate send
        session.commit()
        
        h_after = session.query(RewardHistory).filter_by(user_id=user.id, is_notified=False).count()
        assert h_after == 0, "Should be no pending notifications"
        print("[OK] Batch status updated.")
        
        # Cleanup
        session.query(QueueEntry).filter_by(user_id=user.id).delete()
        session.query(RewardHistory).filter_by(user_id=user.id).delete()
        # Don't delete user/char/queue to avoid breaking ForeignKeys if needed elsewhere, 
        # or just delete if it's a test DB. Assuming dev DB, let's keep it clean.
        session.delete(user) # Cascades
        if q.name == "TestQueue": session.delete(q)
        session.commit()
        print("\n[OK] CLEANUP COMPLETE.")

if __name__ == "__main__":
    init_db()
    test_features()
