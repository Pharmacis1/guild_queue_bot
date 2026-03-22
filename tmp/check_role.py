
import asyncio
from database import AsyncSessionLocal, Character
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Character.nickname, Character.is_main).where(Character.user_id == 1))
        rows = result.all()
        print(f"Characters for User 1: {rows}")

if __name__ == "__main__":
    asyncio.run(main())
