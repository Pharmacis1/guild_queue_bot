import os
import sys

# Add parent directory to path to allow importing from database.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backup_db import perform_backup

from database import Character, session


def clear_data():
    print("WARNING: This will delete ALL linked nicknames and player professions.")
    
    # Auto-backup
    print("creating pre-clear backup...")
    if perform_backup("pre_clear"):
        print("Backup created successfully.")
    else:
        print("Backup FAILED!")
        confirm_bk = input("Continue without backup? (yes/no): ")
        if confirm_bk.lower() != "yes":
            return

    confirm = input("Type 'DELETE' to confirm: ")
    
    if confirm != "DELETE":
        print("Operation cancelled.")
        return

    try:
        # 1. Delete all rows from Character table (unlink users from nicknames)
        num_chars = session.query(Character).delete()
        print(f"Deleted {num_chars} linked nicknames (Character table).")

        # 2. CLEAR columns in Player table (but keep rows/IDs)
        # Set nickname=NULL and class_id=-1 (or default)
        result = session.execute("UPDATE players SET nickname=NULL, class_id=-1")
        print(f"Cleared nicknames and professions for {result.rowcount} players (IDs preserved).")

        session.commit()
        print("Database cleanup successful.")
        
    except Exception as e:
        session.rollback()
        print(f"An error occurred: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    clear_data()
