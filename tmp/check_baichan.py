
import asyncio
from database import AsyncSessionLocal, Player
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Player.nickname).where(Player.nickname.ilike('%Baichan%')))
        names = result.scalars().all()
        print(f"Found: {names}")

if __name__ == "__main__":
    asyncio.run(main())
