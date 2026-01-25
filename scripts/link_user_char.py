import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from database import session, User, Character

def link_char(tg_id, char_name):
    try:
        user = session.query(User).filter_by(telegram_id=tg_id).first()
        if not user:
            print(f"❌ User {tg_id} not found.")
            return

        # Check if exists
        char = session.query(Character).filter_by(user_id=user.id, nickname=char_name).first()
        if char:
            print(f"✅ Character '{char_name}' already linked to {user.username}.")
            if not char.is_main:
                char.is_main = True
                session.commit()
                print("   Set as main.")
            return

        # Add
        new_char = Character(user_id=user.id, nickname=char_name, is_main=True)
        session.add(new_char)
        session.commit()
        print(f"✅ Linked '{char_name}' to {user.username} (Main=True).")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    link_char(5075198340, "Morwen")
