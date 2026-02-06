import glob
import os
import shutil
import sys

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_NAME = os.path.join(BASE_DIR, "guild_bot.db")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
MANUAL_BACKUP = os.path.join(BASE_DIR, "guild_bot.db.bak")


def get_latest_backup():
    # Look for files matching the pattern in backups/
    files = glob.glob(os.path.join(BACKUP_DIR, "guild_bot_*.db"))
    if not files:
        return None
    # Sort by modification time, newest first
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


def restore(target_backup=None, skip_confirm=False):
    if not target_backup:
        # Try to find latest in backups/
        latest = get_latest_backup()
        if latest:
            target_backup = latest
            print(f"Found latest automated backup: {os.path.basename(target_backup)}")
        elif os.path.exists(MANUAL_BACKUP):
            target_backup = MANUAL_BACKUP
            print(f"No automated backups found. Using manual backup: {os.path.basename(target_backup)}")
        else:
            print("Error: No backups found within 'backups/' directory or 'guild_bot.db.bak'!")
            return

    if not os.path.exists(target_backup):
        print(f"Error: Backup file '{target_backup}' not found!")
        return

    print(f"Restoring '{DB_NAME}' from '{target_backup}'...")
    print("WARNING: This will overwrite the current database!")

    # Confirm
    if not skip_confirm:
        try:
            confirm = input("Are you sure? (y/n): ")
        except EOFError:
            confirm = "y"  # Assume yes if running non-interactively/piped, though risky. Better to be explicit.

        if confirm.lower() != "y":
            print("Restore cancelled.")
            return

    try:
        # Create a safety backup of the current state before overwriting
        if os.path.exists(DB_NAME):
            safety_backup = os.path.join(BACKUP_DIR, "pre_restore_safety.db")
            shutil.copy(DB_NAME, safety_backup)
            print(f"Created safety backup of current state: {os.path.basename(safety_backup)}")

        shutil.copy(target_backup, DB_NAME)
        print("Success! Database has been restored.")
    except Exception as e:
        print(f"Error restoring database: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        restore(sys.argv[1])
    else:
        restore()
