import os
import sys

# Add project root to sys.path
sys.path.append(os.getcwd())

from database import User, session


def promote(tg_id):
    try:
        user = session.query(User).filter_by(telegram_id=tg_id).first()
        if not user:
            print(f"User with Telegram ID {tg_id} not found.")
            return
        
        user.is_master = True
        session.commit()
        print(f"✅ User {user.username} (ID: {tg_id}) is now a MASTER/ADMIN.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/promote_user.py <telegram_id>")
    else:
        promote(int(sys.argv[1]))
