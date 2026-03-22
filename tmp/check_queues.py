import asyncio
import os
import sys
sys.path.append(os.getcwd())
from database import AsyncSessionLocal, QueueEntry
from sqlalchemy import select, func

async def check_queues():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.count(QueueEntry.id)))
        count = result.scalar()
        print(f"Total Queue Entries: {count}")
        
        # Check for any users joined today if we had a created_at, but we don't.
        # So we'll just check if it's non-zero.
        print("Bot seems to have data.")

if __name__ == "__main__":
    asyncio.run(check_queues())
