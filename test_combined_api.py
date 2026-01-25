import requests
import sqlite3
import json

DB_NAME = "guild_bot.db"

def get_valid_role_id():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT role_id, nickname FROM players LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        return row
    except Exception as e:
        print(f"DB Error: {e}")
    return None

def test_combined(port, role_id, current_nick):
    url = f"http://localhost:{port}/api/update_player"
    
    # Test Payload: Change Nickname + Update Status + Update Class
    new_nick = current_nick + "_TEST"
    payload = {
        "role_id": role_id, 
        "nickname": new_nick,
        "class_id": 1, # Warrior or something
        "in_clan": False 
    }
    
    print(f"Testing {url} with payload {payload}...")
    try:
        response = requests.post(url, json=payload, timeout=5)
        print(f"Status: {response.status_code}")
        print(f"Body: {response.text[:200]}") 
        
        if response.status_code == 200:
             print("SUCCESS!")
             # Revert changes
             cleanup_payload = {
                 "role_id": role_id,
                 "nickname": current_nick,
                 "in_clan": True
             }
             requests.post(url, json=cleanup_payload)
             print("Reverted cleanup.")
             return True
        else:
             print("FAILED")
             return False

    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    data = get_valid_role_id()
    if not data:
        print("No players found")
        exit(1)
        
    role_id, nick = data
    if not nick: nick = "Unknown"
    
    print(f"Using role_id: {role_id}, Nick: {nick}")
    
    test_combined(8081, role_id, nick)
