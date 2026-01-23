import sqlite3
import random
import shutil
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from consts import CLASSES

DB_NAME = "guild_bot.db"
BACKUP_NAME = "guild_bot.db.bak"

def randomize():
    # 1. Backup
    if os.path.exists(DB_NAME):
        shutil.copy(DB_NAME, BACKUP_NAME)
        print(f"Backup created: {BACKUP_NAME}")
    else:
        print("Database not found!")
        return

    # 2. Randomize
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Get all players
    cursor.execute("SELECT role_id FROM players")
    players = cursor.fetchall()
    
    print(f"Found {len(players)} players. Updating...")
    
    class_ids = list(CLASSES.keys())
    
    # Optional: List of cool nicknames
    prefixes = ["Shadow", "Light", "Dark", "Holy", "Iron", "Gold", "Silver", "Mystic", "Cyber", "Elder"]
    suffixes = ["Warrior", "Mage", "Knight", "Rogue", "Priest", "Hunter", "Slayer", "Guardian", "Wolf", "Dragon"]
    
    for (role_id,) in players:
        # Generate random nickname
        nick = f"{random.choice(prefixes)}{random.choice(suffixes)}_{role_id % 100}"
        
        # Pick random class
        cid = random.choice(class_ids)
        
        cursor.execute("UPDATE players SET nickname = ?, class_id = ? WHERE role_id = ?", (nick, cid, role_id))
        
    conn.commit()
    conn.close()
    print("Done! All players have random data.")

if __name__ == "__main__":
    randomize()
