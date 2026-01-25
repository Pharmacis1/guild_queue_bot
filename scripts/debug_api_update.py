import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from routers.api import update_nickname, update_class, update_status
from consts import CLASSES

# Mock Request class
class MockRequest:
    def __init__(self, json_data):
        self._json = json_data
        
    async def json(self):
        return self._json

async def test_update():
    print("--- Testing API Updates for Player 1337 (Test) ---")
    
    # Prerequisite: Ensure player exists (or use existing ID 1)
    # Using ID 1 as per user report (it exists)
    role_id = 1
    
    # 1. Test Nickname Update
    print(f"\n[1] Testing update_nickname for ID {role_id}...")
    req = MockRequest({"role_id": str(role_id), "nickname": "TestNick"})
    res = await update_nickname(req)
    print(f"Result: {res}")
    
    # 2. Test Class Update
    print(f"\n[2] Testing update_class for ID {role_id}...")
    # class_id = -1 (Unknown)
    req = MockRequest({"role_id": str(role_id), "class_id": -1})
    res = await update_class(req)
    print(f"Result: {res}")
    
    # 3. Test Status Update
    print(f"\n[3] Testing update_status for ID {role_id}...")
    req = MockRequest({"role_id": str(role_id), "in_clan": True})
    res = await update_status(req)
    print(f"Result: {res}")
    
    # 4. Test Error Case (Invalid ID)
    print(f"\n[4] Testing Invalid ID...")
    req = MockRequest({"role_id": "9999999", "nickname": "Ghost"})
    res = await update_nickname(req)
    print(f"Result: {res}")

if __name__ == "__main__":
    try:
        asyncio.run(test_update())
    except Exception as e:
        print(f"CRASH: {e}")
