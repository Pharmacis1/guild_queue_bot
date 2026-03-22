import asyncio
import os
import sys
sys.path.append(os.getcwd())
from database import AsyncSessionLocal, MessageLog
from sqlalchemy import select, desc

async def check_messages():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(MessageLog).order_by(desc(MessageLog.timestamp)).limit(5)
        )
        messages = result.scalars().all()
        if not messages:
            print("No messages found in DB")
            return
        for m in messages:
            safe_text = m.text[:50].encode('ascii', 'replace').decode('ascii')
            print(f"[{m.timestamp}] {m.user_name}: {safe_text}")

if __name__ == "__main__":
    asyncio.run(check_messages())
