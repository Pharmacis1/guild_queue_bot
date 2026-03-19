import pytest
from sqlalchemy import text
from database import Base, engine

@pytest.mark.asyncio
async def test_all_sequences_health():
    """
    Diagnostic test to ensure all PostgreSQL sequences are ahead of current MAX(id).
    This test is primarily useful when run against a persistent database (dev/staging/prod).
    """
    # This test is specific to PostgreSQL
    if engine.url.drivername != "postgresql+asyncpg":
        pytest.skip("This test is only relevant for PostgreSQL")

    async with engine.connect() as conn:
        # 1. Get all tables with an 'id' column
        query = text("""
            SELECT table_name
            FROM information_schema.columns
            WHERE column_name = 'id' 
              AND table_schema = 'public'
              AND table_name NOT IN (SELECT table_name FROM information_schema.views WHERE table_schema = 'public');
        """)
        
        result = await conn.execute(query)
        tables = [row[0] for row in result.fetchall()]
        
        failures = []
        
        for table in tables:
            # 2. Find the sequence name for the 'id' column
            seq_query = text(f"SELECT pg_get_serial_sequence('\"{table}\"', 'id')")
            seq_name_res = await conn.execute(seq_query)
            seq_name = seq_name_res.scalar()
            
            if not seq_name:
                continue
                
            # 3. Get MAX(id) and the next value of the sequence
            # Note: We use last_value and is_called from pg_sequences or a similar view
            # In PG 10+, pg_sequences is the standard way.
            health_query = text(f"""
                SELECT 
                    COALESCE((SELECT MAX(id) FROM "{table}"), 0) as max_id,
                    (SELECT last_value FROM {seq_name}) as last_val,
                    (SELECT is_called FROM {seq_name}) as is_called
            """)
            
            try:
                h_res = await conn.execute(health_query)
                row = h_res.fetchone()
                max_id, last_val, is_called = row
                
                next_val = last_val + 1 if is_called else last_val
                
                if next_val <= max_id:
                    failures.append(f"Table '{table}': sequence '{seq_name}' is at {next_val}, but MAX(id) is {max_id}")
            except Exception as e:
                # Some tables might not have standard sequence access
                print(f"Skipping health check for {table} due to: {e}")

        if failures:
            pytest.fail("\n".join(failures))

@pytest.mark.asyncio
async def test_afk_history_insertion_sanity(async_test_session):
    """
    Sanity test to ensure we can insert into afk_history without errors.
    """
    from database import AFKHistory, User
    from datetime import datetime, timedelta
    
    # Create a user
    user = User(telegram_id=999999, username="test_afk_sanity")
    async_test_session.add(user)
    await async_test_session.flush()
    
    # Try to add an AFK record
    record = AFKHistory(
        user_id=user.id,
        start_date=datetime.now(),
        end_date=datetime.now() + timedelta(days=7),
        reason="Sanity Test"
    )
    async_test_session.add(record)
    await async_test_session.commit()
    
    assert record.id is not None
