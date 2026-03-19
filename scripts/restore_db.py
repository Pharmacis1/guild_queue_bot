import glob
import os
import sys
import shutil
import subprocess
from dotenv import load_dotenv

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, '.env'))

from sqlalchemy.engine import make_url

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
    print(f"Failed to parse DATABASE_URL: {e}")
    DB_USER = "guild_user"
    DB_PASS = "your_password"
    DB_HOST = "localhost"
    DB_PORT = 5432
    DB_NAME = "guild_bot"

def get_pg_tool_path(tool_name="pg_restore"):
    if shutil.which(tool_name):
        return tool_name
        
    custom_path = os.getenv("PG_BIN_PATH")
    if custom_path:
        full_path = os.path.join(custom_path, f"{tool_name}.exe" if os.name == 'nt' else tool_name)
        if os.path.exists(full_path):
            return full_path

    if os.name == "nt":
        for version in ["16", "15", "14", "13", "12", "11"]:
            common_path = fr"C:\Program Files\PostgreSQL\{version}\bin\{tool_name}.exe"
            if os.path.exists(common_path):
                return common_path

    return tool_name


def get_latest_backup():
    # Look for files matching the pattern in backups/
    files = glob.glob(os.path.join(BACKUP_DIR, "guild_bot_*.sql"))
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
        else:
            print("Error: No .sql backups found within 'backups/' directory!")
            return

    if not os.path.exists(target_backup):
        print(f"Error: Backup file '{target_backup}' not found!")
        return

    print(f"Restoring '{DB_NAME}' from '{target_backup}'...")
    print("WARNING: This will overwrite the current PostgreSQL database!")

    # Confirm
    if not skip_confirm:
        try:
            confirm = input("Are you sure? (y/n): ")
        except EOFError:
            confirm = "n"

        if confirm.lower() != "y":
            print("Restore cancelled.")
            return

    env = os.environ.copy()
    if DB_PASS:
        env["PGPASSWORD"] = DB_PASS

    pg_restore_path = get_pg_tool_path("pg_restore")

    cmd = [
        pg_restore_path,
        "-U", DB_USER,
        "-h", DB_HOST,
        "-p", str(DB_PORT),
        "-d", DB_NAME,
        "-c", # clean (drop) database objects before recreating
        "--if-exists",
        target_backup
    ]

    try:
        from scripts.backup_db import perform_backup
        
        # Create a safety backup of the current state before overwriting
        print("Creating a safety backup of current state before restoring...")
        perform_backup(force_suffix="pre_restore_safety")

        print(f"Running {pg_restore_path} for database {DB_NAME}...")
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        
        # Note: pg_restore might return non-zero exit codes for non-fatal errors during -c, so check carefully
        if result.returncode != 0 and "FATAL" in result.stderr:
            print(f"Error restoring database: {result.stderr}")
        else:
            if result.stderr:
                print(f"pg_restore messages:\n{result.stderr}")
            print("Success! Database has been restored.")
    except subprocess.CalledProcessError as e:
        print(f"Error running pg_restore: {e.stderr}")
    except FileNotFoundError:
        print("pg_restore executable not found. Ensure PostgreSQL tools are heavily installed and in PATH. Or set PG_BIN_PATH in .env")
    except Exception as e:
        print(f"Error restoring database: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        restore(sys.argv[1])
    else:
        restore()
