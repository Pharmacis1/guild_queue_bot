import requests
import sqlite3
import json

DB_NAME = "guild_bot.db"

def get_valid_role_id():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT role_id FROM players LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception as e:
        print(f"DB Error: {e}")
    return None

def test_endpoint(port, role_id):
    url = f"http://localhost:{port}/api/update_status"
    payload = {"role_id": role_id, "in_clan": False}
    print(f"Testing {url} with payload {payload}...")
    try:
        response = requests.post(url, json=payload, timeout=5)
        print(f"Status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type')}")
        print(f"Body: {response.text[:200]}") # Show first 200 chars
        return True
    except requests.exceptions.ConnectionError:
        print(f"Connection failed on port {port}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    role_id = get_valid_role_id()
    if not role_id:
        print("Could not get a valid role_id from DB. Is DB empty?")
        # Use a dummy one, might return 404 but should still be JSON
        role_id = 999999
    
    print(f"Using role_id: {role_id}")
    
    # Test typical ports
    if not test_endpoint(8081, role_id):
        test_endpoint(8001, role_id)
