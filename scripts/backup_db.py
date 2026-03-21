import datetime
import logging
import os
import shutil
import sys
import subprocess

from dotenv import load_dotenv

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, '.env'))

from logic.google_drive import GoogleDriveService  # noqa: E402
from sqlalchemy.engine import make_url

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("backup_db")

BACKUP_DIR = os.path.join(BASE_DIR, "backups")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://guild_user:your_password@localhost/guild_bot")

try:
    url = make_url(DATABASE_URL)
    DB_USER = url.username
    DB_PASS = url.password
    DB_HOST = url.host
    DB_PORT = url.port or 5432
    DB_NAME = url.database
except Exception as e:
    logger.error(f"Failed to parse DATABASE_URL: {e}")
    DB_USER = "guild_user"
    DB_PASS = "your_password"
    DB_HOST = "localhost"
    DB_PORT = 5432
    DB_NAME = "guild_bot"

def get_pg_tool_path(tool_name="pg_dump"):
    # First, try to see if it's in PATH
    if shutil.which(tool_name):
        return tool_name
        
    # Check custom PG_BIN_PATH from .env
    custom_path = os.getenv("PG_BIN_PATH")
    if custom_path:
        full_path = os.path.join(custom_path, f"{tool_name}.exe" if os.name == 'nt' else tool_name)
        if os.path.exists(full_path):
            return full_path

    # Check common Postgres install locations on Windows
    if os.name == "nt":
        for version in ["16", "15", "14", "13", "12", "11"]:
            common_path = fr"C:\Program Files\PostgreSQL\{version}\bin\{tool_name}.exe"
            if os.path.exists(common_path):
                return common_path

    return tool_name

def perform_backup(force_suffix=None):
    """
    Creates a backup of the PostgreSQL database using pg_dump.
    :param force_suffix: Optional string to append to filename (e.g. 'manual', 'pre_clear')
    """
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        logger.info(f"Created backup directory: {BACKUP_DIR}")

    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")

    suffix = f"_{force_suffix}" if force_suffix else ""
    filename = f"guild_bot_{timestamp}{suffix}.sql"
    backup_path = os.path.join(BACKUP_DIR, filename)

    env = os.environ.copy()
    if DB_PASS:
        env["PGPASSWORD"] = DB_PASS

    pg_dump_path = get_pg_tool_path("pg_dump")

    cmd = [
        pg_dump_path,
        "-U", DB_USER,
        "-h", DB_HOST,
        "-p", str(DB_PORT),
        "-F", "c", # Custom format (compressed)
        "-f", backup_path,
        DB_NAME
    ]

    try:
        logger.info(f"Running {pg_dump_path} for database {DB_NAME}")
        subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
        logger.info(f"Backup created successfully: {backup_path}")

        # Upload to Google Drive
        try:
            drive_service = GoogleDriveService()
            drive_service.upload_file(backup_path)
        except Exception as e:
            logger.error(f"Google Drive upload failed: {e}")
            print(f"❌ [Backup] Google Drive upload failed: {e}")

        # Cleanup old backups (keep last 7 days + 5 recent)
        cleanup_old_backups()
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to run pg_dump: {e.stderr}")
        print(f"❌ [Backup] pg_dump failed: {e.stderr}")
        return False
    except FileNotFoundError:
        logger.error("pg_dump executable not found. Ensure PostgreSQL tools are heavily installed and in PATH. Or set PG_BIN_PATH in .env")
        print("❌ [Backup] pg_dump not found.")
        return False
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        print(f"❌ [Backup] Failed to create backup: {e}")
        return False


def cleanup_old_backups(max_files=20, max_days=7):
    """
    Removes old backups to save space.
    """
    try:
        files = []
        for f in os.listdir(BACKUP_DIR):
            if any(f.endswith(ext) for ext in [".sql", ".db", ".bak"]) and "guild_bot_" in f:
                path = os.path.join(BACKUP_DIR, f)
                files.append(path)

        # Sort by modification time (newest first)
        files.sort(key=os.path.getmtime, reverse=True)

        if len(files) <= max_files:
            return

        # Keep max_files latest.
        for old_file in files[max_files:]:
            os.remove(old_file)
            logger.info(f"Removed old backup: {old_file}")

    except Exception as e:
        logger.error(f"Error cleaning up backups: {e}")


if __name__ == "__main__":
    perform_backup("manual_run")
