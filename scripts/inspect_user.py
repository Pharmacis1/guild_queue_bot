import os
import sys

# Add project root to sys.path
sys.path.append(os.getcwd())

from database import Character, User, session


def inspect(tg_id):
    try:
        user = session.query(User).filter_by(telegram_id=tg_id).first()
        if not user:
            print(f"❌ User with Telegram ID {tg_id} not found in DB.")
            return

        print(f"✅ User Found: ID={user.id}, Username={user.username}, IsMaster={user.is_master}")

        chars = session.query(Character).filter_by(user_id=user.id).all()
        if chars:
            print(f"✅ Found {len(chars)} characters:")
            for c in chars:
                print(f"   - ID={c.id}, Nickname='{c.nickname}', IsMain={c.is_main}")
        else:
            print("⚠️ No characters found for this user.")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/inspect_user.py <telegram_id>")
    else:
        inspect(int(sys.argv[1]))
