import sqlite3
import os

# Try default local paths, prioritize the production name if present
possible_paths = [
    "guild_bot.db",  # Production common name
    "guild_bot_2026-02-13_13-20-30_manual_user.db", # Manual dump name
]

db_path = None
for p in possible_paths:
    if os.path.exists(p):
        db_path = p
        break

if not db_path:
    # Fallback to absolute path dev environment if none found in current dir
    dev_path = r"c:\dev\guild_queue_bot\guild_bot_2026-02-13_13-20-30_manual_user.db"
    if os.path.exists(dev_path):
        db_path = dev_path

if not db_path:
    print("Database file not found!")
    print(f"Checked: {possible_paths}")
    exit(1)

print(f"Using database: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

target_timestamp = 1912886640
target_event_type = 41785

print(f"Checking for corrupted row with timestamp {target_timestamp}...")

cursor.execute("SELECT * FROM events WHERE timestamp = ? AND event_type = ?", (target_timestamp, target_event_type))
rows = cursor.fetchall()

if not rows:
    print("Row not found! It might have been deleted already.")
else:
    print(f"Found {len(rows)} row(s):")
    for row in rows:
        print(row)
    
    print("Deleting...")
    cursor.execute("DELETE FROM events WHERE timestamp = ? AND event_type = ?", (target_timestamp, target_event_type))
    conn.commit()
    print(f"Deleted {cursor.rowcount} row(s).")

# Verify
cursor.execute("SELECT * FROM events WHERE timestamp = ? AND event_type = ?", (target_timestamp, target_event_type))
remaining = cursor.fetchall()
if not remaining:
    print("Verification successful: Row is gone.")
else:
    print("Verification FAILED: Row still exists!")

conn.close()
