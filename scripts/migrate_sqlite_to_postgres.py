import asyncio
import os
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import sessionmaker

# Import models
from database import Base, User, Character, QueueType, QueueEntry, RewardHistory, \
    ScheduledAnnouncement, Player, Event, Item, AFKHistory, ObserverCache, \
    ConstantParty, PartyMember, FaqTopic, FaqMessage, MessageLog, SummaryState, Settings

# Configuration
SQLITE_URL = "sqlite:///guild_bot.db"
POSTGRES_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://guild_user:your_password@localhost/guild_bot")

async def migrate():
    # Source (SQLite - sync is easier for reading all at once)
    sqlite_engine = create_engine(SQLITE_URL)
    SqliteSession = sessionmaker(bind=sqlite_engine)
    sqlite_session = SqliteSession()

    # Destination (Postgres - async)
    pg_engine = create_async_engine(POSTGRES_URL)
    PgSession = async_sessionmaker(bind=pg_engine, expire_on_commit=False)

    print(f"Starting migration from {SQLITE_URL} to PostgreSQL...")

    # Create tables in Postgres
    async with pg_engine.begin() as conn:
        # print("Dropping existing tables to fix types...")
        # await conn.run_sync(Base.metadata.drop_all)
        print("Ensuring tables exist...")
        await conn.run_sync(Base.metadata.create_all)

    models = [
        User, Player, Settings, QueueType, ConstantParty, FaqTopic, # Parents first
        Character, QueueEntry, RewardHistory, ScheduledAnnouncement, 
        Event, Item, AFKHistory, ObserverCache, PartyMember, 
        FaqMessage, MessageLog, SummaryState
    ]

    async with PgSession() as pg_session:
        # Disable FK checks for migration
        await pg_session.execute(text("SET session_replication_role = 'replica';"))
        
        for model in models:
            name = model.__tablename__
            print(f"Migrating {name}...")
            
            # Fetch from SQLite
            items = sqlite_session.query(model).all()
            if not items:
                print(f"  No data in {name}, skipping.")
                continue
            
            # Merge into Postgres
            with pg_session.no_autoflush:
                for item in items:
                    sqlite_session.expunge(item)
                    await pg_session.merge(item)
            
            await pg_session.commit()
            print(f"  Successfully migrated {len(items)} records to {name}.")
            
        # Re-enable FK checks
        await pg_session.execute(text("SET session_replication_role = 'origin';"))
        await pg_session.commit()

    print("Migration completed successfully!")

if __name__ == "__main__":
    asyncio.run(migrate())
