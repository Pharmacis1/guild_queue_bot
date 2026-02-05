from sqlalchemy import text

from database import engine, init_db

print("Running migration...")
init_db()

print("Checking schema...")
with engine.connect() as conn:
    try:
        conn.execute(text("SELECT auto_requeue FROM queue_entries LIMIT 1"))
        print("✅ auto_requeue exists")
    except Exception as e:
        print(f"❌ auto_requeue MISSING: {e}")

    try:
        conn.execute(text("SELECT is_notified FROM reward_history LIMIT 1"))
        print("✅ is_notified exists")
    except Exception as e:
        print(f"❌ is_notified MISSING: {e}")
