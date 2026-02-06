from sqlalchemy import text

from database import engine


def migrate():
    print("Migrating database...")
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN pending_request_nick VARCHAR"))
            print("✅ Added pending_request_nick column.")
        except Exception as e:
            print(f"⚠️ Column might already exist or error: {e}")


if __name__ == "__main__":
    migrate()
