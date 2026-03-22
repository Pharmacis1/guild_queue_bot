
import asyncio
from database import AsyncSessionLocal, User
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.id, User.telegram_id, User.username).where(User.id == 1))
        row = result.first()
        print(f"User 1: {row}")

if __name__ == "__main__":
    asyncio.run(main())
