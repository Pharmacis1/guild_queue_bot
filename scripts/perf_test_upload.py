import asyncio
import time
import logging
from unittest.mock import patch, MagicMock
from logic.log_importer import process_log_upload
from database import AsyncSessionLocal, Player, Event, Base, engine

# Setup logging
logging.basicConfig(level=logging.INFO)

async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def test_performance():
    # 1. Generate large data
    num_records = 5000
    mock_data = []
    for i in range(num_records):
        mock_data.append({
            "date": f"2024-01-01 12:00:{i%60:02d}",
            "timestamp": 1704100000 + i,
            "role_id": 1000 + (i % 500), # 500 unique players
            "action_type": 1, # Вклад (Доблесть)
            "description": f"Вклад (Доблесть): {i}",
            "raw_params": f"{i}, 0, 0",
        })

    # 2. Mock parse_board_file
    with patch("logic.log_importer.parse_board_file", return_value=mock_data):
        with patch("logic.log_importer.AsyncSessionLocal", return_value=AsyncSessionLocal()):
            print(f"Starting upload of {num_records} records...")
            start_time = time.time()
            
            result, missing_ids, should_run = await process_log_upload("dummy.bin")
            
            end_time = time.time()
            duration = end_time - start_time
            
            print(f"Result: {result}")
            print(f"Time taken: {duration:.2f} seconds")
            print(f"Records per second: {num_records / duration:.2f}")

            if result["status"] == "ok":
                print("SUCCESS: Performance test passed.")
            else:
                print(f"FAILED: {result.get('message')}")

if __name__ == "__main__":
    # We need to ensure DB is initialized if using a local sqlite for test
    # But usually this project uses Postgres. We'll use the actual DB configured.
    asyncio.run(test_performance())
