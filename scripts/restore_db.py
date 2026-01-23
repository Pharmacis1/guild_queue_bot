import shutil
import os

DB_NAME = "guild_bot.db"
BACKUP_NAME = "guild_bot.db.bak"

def restore():
    if not os.path.exists(BACKUP_NAME):
        print(f"Error: Backup file '{BACKUP_NAME}' not found!")
        return

    # Safety: check if we are overwriting something
    if os.path.exists(DB_NAME):
        print(f"Overwriting current '{DB_NAME}' with backup...")
    else:
        print(f"Restoring '{DB_NAME}' from backup...")

    try:
        shutil.copy(BACKUP_NAME, DB_NAME)
        print("Success! Database has been restored from backup.")
    except Exception as e:
        print(f"Error restoring database: {e}")

if __name__ == "__main__":
    restore()
