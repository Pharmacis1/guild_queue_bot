import asyncio
import os
import sys

# Add parent directory to path to absolute import database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from database import (
    Base, User, Settings, Character, QueueType, QueueEntry, RewardHistory, 
    ScheduledAnnouncement, Player, Event, Item, AFKHistory, ObserverCache, 
    ConstantParty, PartyMember, FaqTopic, FaqMessage, MessageLog, SummaryState
)
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

# The SQLite database path
sqlite_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "guild_bot_2026-03-20_06-29-42_manual_user.db")
sqlite_url = f"sqlite:///{sqlite_path.replace(chr(92), '/')}" 

sqlite_engine = create_engine(sqlite_url)
SqliteSession = sessionmaker(bind=sqlite_engine)

pg_url = os.getenv("DATABASE_URL")
if not pg_url:
    print("No DATABASE_URL found in .env properly.")
    sys.exit(1)

pg_engine = create_async_engine(pg_url, echo=False)
PgSession = async_sessionmaker(bind=pg_engine, expire_on_commit=False)


async def main():
    print(f"Connecting to SQLite: {sqlite_path}")
    print(f"Connecting to PostgreSQL: {pg_url}")
    
    # 1. Reset tables in PG to avoid duplication
    async with pg_engine.begin() as conn:
        print("Dropping all existing PG tables...")
        await conn.run_sync(Base.metadata.drop_all)
        print("Recreating PG tables from current models...")
        await conn.run_sync(Base.metadata.create_all)

    # 2. Ordered tables so FKs don't break
    tables_to_migrate = [
        User, Settings, QueueType, Item, ConstantParty, FaqTopic,
        Character, QueueEntry, RewardHistory, ScheduledAnnouncement, Player, Event, 
        AFKHistory, ObserverCache, PartyMember, FaqMessage, MessageLog, SummaryState
    ]

    sqlite_session = SqliteSession()
    
    async with PgSession() as pg_session:
        for model in tables_to_migrate:
            print(f"Migrating {model.__tablename__}...")
            records = sqlite_session.query(model).all()
            print(f"  Found {len(records)} records in SQLite.")
            
            for item in records:
                # Copy values
                data = {col: getattr(item, col) for col in model.__table__.columns.keys()}
                new_item = model(**data)
                pg_session.add(new_item)
            
            try:
                await pg_session.commit()
                print(f"  Success for {model.__tablename__}")
            except Exception as e:
                print(f"  Error inserting {model.__tablename__}: {e}")
                await pg_session.rollback()

    sqlite_session.close()

    # 3. Handle sequences for Postgres
    # PostgreSQL auto-incrementing primary keys (SERIAL/IDENTITY columns) need resetting
    # if we manually inserted values for them.
    print("Fixing sequences...")
    async with pg_engine.begin() as conn:
        for model in tables_to_migrate:
            table_name = model.__tablename__
            
            # Find the primary key column (usually 'id')
            pk_col = next(iter(model.__table__.primary_key.columns))
            
            # We don't need to fix seq if it's not an Integer auto-incrementing key, or if it isn't named id
            if pk_col.name == "id" and str(pk_col.type) in ("INTEGER", "BIGINT"):
                seq_sql = f"SELECT setval('{table_name}_id_seq', COALESCE((SELECT MAX(id)+1 FROM {table_name}), 1), false);"
                try:
                    from sqlalchemy import text
                    await conn.execute(text(seq_sql))
                    print(f"  Reset sequence for {table_name}")
                except Exception as e:
                    print(f"  Could not reset sequence for {table_name}: {e}")

    print("Migration complete!")

if __name__ == "__main__":
    asyncio.run(main())
