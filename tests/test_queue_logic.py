import pytest

from database import Character, QueueEntry, QueueType, Settings, User
from logic.queue_ops import join_queue, leave_queue


# Helper to create context in test DB
async def setup_test_data(conn):
    # User
    await conn.execute("INSERT INTO users (telegram_id, username, is_master) VALUES (12345, 'tester', 0)")
    # Get ID
    async with conn.execute("SELECT id FROM users WHERE telegram_id=12345") as cursor:
        uid = (await cursor.fetchone())[0]
        
    # Queue
    await conn.execute("INSERT INTO queue_types (name, is_active) VALUES ('TestQueue', 1)")
    async with conn.execute("SELECT id FROM queue_types WHERE name='TestQueue'") as cursor:
        qid = (await cursor.fetchone())[0]

    # Character
    await conn.execute("INSERT INTO characters (user_id, nickname, is_main) VALUES (?, 'TestChar', 1)", (uid,))
    async with conn.execute("SELECT id FROM characters WHERE nickname='TestChar'") as cursor:
        cid = (await cursor.fetchone())[0]
        
    # Settings (Limit)
    await conn.execute("INSERT INTO settings (key, value) VALUES ('default_limit', '1')")
    
    await conn.commit()
    return uid, qid, cid

# Since logic/queue_ops.py uses Synchronous SQLAlchemy Session, we need a Synchronous Test!
# BUT our app is Async (FastAPI/Aiogram), but database.py uses Sync Session for some parts?
# Let's check handlers/user.py imports.
# It imports `session` from `database`. `database.py` creates `session = Session()`.
# So the handlers use SYNC DB calls.

# This means our TEST must also use Sync Session or we use the hybrid approach.
# In `queue_ops.py`, we typed `session: Session`.
# So we should pass a SQLAlchemy Session, not aiosqlite connection.

# Our fixture `test_db_session` returns a PATH string.
# We need a fixture that returns a SQLAlchemy Session bound to that path.

@pytest.fixture
def sync_test_session(test_db_session):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    # Connect to the temp DB path provided by fixture
    engine = create_engine(f'sqlite:///{test_db_session}')
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_join_queue_success(sync_test_session):
    session = sync_test_session
    
    # Setup Data (Sync)
    user = User(telegram_id=111, username="u1", is_master=False)
    session.add(user)
    session.commit()
    
    q = QueueType(name="Q1", is_active=True)
    session.add(q)
    session.commit()
    
    char = Character(user_id=user.id, nickname="C1", is_main=True)
    session.add(char)
    session.commit()
    
    # Test Join
    success, msg, entry = join_queue(session, user.id, q.id, char.id, is_auto=False)
    
    assert success is True
    assert "Записан" in msg
    assert entry is not None

    
    # Verify DB
    entry = session.query(QueueEntry).filter_by(user_id=user.id, queue_type_id=q.id).first()
    assert entry is not None
    assert entry.character_name == "C1"
    assert entry.auto_requeue is False

def test_join_queue_limit(sync_test_session):
    session = sync_test_session
    
    # Setup
    user = User(telegram_id=222, username="u2")
    session.add(user)
    session.add(Settings(key="default_limit", value="1"))
    session.commit()
    
    q1 = QueueType(name="Q1")
    q2 = QueueType(name="Q2")
    session.add_all([q1, q2])
    session.commit()
    
    char = Character(user_id=user.id, nickname="C2", is_main=True)
    session.add(char)
    session.commit()
    
    # Join Q1 (Limit 1/1)
    join_queue(session, user.id, q1.id, char.id, is_auto=False)
    
    # Try Join Q2 (Should fail)
    success, msg, _ = join_queue(session, user.id, q2.id, char.id, is_auto=False)
    
    assert success is False
    assert "Лимит" in msg

def test_leave_queue(sync_test_session):
    session = sync_test_session
    
    user = User(telegram_id=333, username="u3")
    session.add(user)
    q = QueueType(name="Q3")
    session.add(q)
    session.commit()
    
    # Add Entry manually
    session.add(QueueEntry(user_id=user.id, queue_type_id=q.id, character_name="C3"))
    session.commit()
    
    # Test Leave
    success, msg, entry = leave_queue(session, user.id, q.id)
    
    assert success is True
    assert entry.character_name == "C3"
    
    # Verify Gone
    assert session.query(QueueEntry).filter_by(user_id=user.id, queue_type_id=q.id).first() is None

def test_join_queue_auto(sync_test_session):
    session = sync_test_session
    user = User(telegram_id=444, username="u4")
    session.add(user)
    q = QueueType(name="Q4")
    session.add(q)
    char = Character(user_id=user.id, nickname="C4", is_main=True)
    session.add(char)
    session.commit()
    
    success, msg, entry = join_queue(session, user.id, q.id, char.id, is_auto=True)
    
    assert success is True
    assert entry.auto_requeue is True
    assert "Авто" in msg
