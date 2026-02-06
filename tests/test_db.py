import asyncio
from datetime import datetime, timedelta

from web_database import get_data_from_db


async def test():
    today = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    print(f"Testing fetch from {start} to {today}")

    try:
        data, s, e, intervals = await get_data_from_db(start, today)
        print(f"Start: {s}, End: {e}")
        print(f"Rows found: {len(data)}")
        if len(data) > 0:
            print("First row:", data[0])
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    asyncio.run(test())
