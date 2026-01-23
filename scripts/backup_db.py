import shutil
import os
import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("backup_db")

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_NAME = os.path.join(BASE_DIR, "guild_bot.db")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

def perform_backup(force_suffix=None):
    """
    Creates a backup of the database.
    :param force_suffix: Optional string to append to filename (e.g. 'manual', 'pre_clear')
    """
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        logger.info(f"Created backup directory: {BACKUP_DIR}")

    if not os.path.exists(DB_NAME):
        logger.error(f"Database file not found at {DB_NAME}")
        return False

    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    
    suffix = f"_{force_suffix}" if force_suffix else ""
    filename = f"guild_bot_{timestamp}{suffix}.db"
    backup_path = os.path.join(BACKUP_DIR, filename)

    try:
        shutil.copy2(DB_NAME, backup_path)
        logger.info(f"Backup created successfully: {backup_path}")
        
        # Cleanup old backups (keep last 7 days + 5 recent)
        cleanup_old_backups()
        return True
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        return False

def cleanup_old_backups(max_files=20, max_days=7):
    """
    Removes old backups to save space.
    """
    try:
        files = []
        for f in os.listdir(BACKUP_DIR):
            if f.endswith(".db") and "guild_bot_" in f:
                path = os.path.join(BACKUP_DIR, f)
                files.append(path)
        
        # Sort by modification time (newest first)
        files.sort(key=os.path.getmtime, reverse=True)
        
        if len(files) <= max_files:
            return

        # Keep recent files, delete older ones that are also older than max_days
        # Actually, simpler logic: keep max_files latest.
        for old_file in files[max_files:]:
            os.remove(old_file)
            logger.info(f"Removed old backup: {old_file}")
            
    except Exception as e:
        logger.error(f"Error cleaning up backups: {e}")

if __name__ == "__main__":
    perform_backup("manual_run")
