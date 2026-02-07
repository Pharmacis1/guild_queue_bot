import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from database import init_db
from logic.dashboard import get_kh_table_data

from routers.api_dashboard import KHResponse

async def test_logic():
    print("--- Testing get_kh_table_data ---")
    
    start = "2026-01-26"
    end = "2026-02-01"
    
    print(f"Calling with start={start}, end={end}")
    
    try:
        data = await get_kh_table_data(
            start=start,
            end=end,
            class_list=None,
            newcomers_mode=None,
            my_nicks=set()
        )
        
        rows = data["rows"]
        print(f"\nReturned {len(rows)} rows from Logic.")
        
        print("\n--- Validating with Pydantic Model ---")
        try:
            resp = KHResponse(
                rows=data["rows"],
                start_date=data["start_date"],
                end_date=data["end_date"]
            )
            print("VALIDATION SUCCESS!")
        except Exception as e:
            print(f"VALIDATION FAILED: {e}")
            if len(rows) > 0:
                print("Sample Row Dict:", rows[0])

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_logic())
