import pytest

from database import Character, QueueEntry, QueueType, Settings, User
from logic.queue_ops import join_queue, leave_queue


from sqlalchemy import select, func

@pytest.mark.asyncio
async def test_join_queue_success(async_test_session):
    session = async_test_session

    # Setup Data
    user = User(telegram_id=111, username="u1", is_master=False)
    session.add(user)
    q = QueueType(name="Q1", is_active=True)
    session.add(q)
    await session.flush()
    
    char = Character(user_id=user.id, nickname="C1", is_main=True)
    session.add(char)
    await session.commit()

    # Test Join
    success, msg, entry = await join_queue(session, user.id, q.id, char.id, is_auto=False)

    assert success is True
    assert "Записан" in msg
    assert entry is not None

    # Verify DB
    result = await session.execute(select(QueueEntry).filter_by(user_id=user.id, queue_type_id=q.id))
    entry = result.scalar_one_or_none()
    assert entry is not None
    assert entry.character_name == "C1"
    assert entry.auto_requeue is False


@pytest.mark.asyncio
async def test_join_queue_limit(async_test_session):
    session = async_test_session

    # Setup
    user = User(telegram_id=222, username="u2")
    session.add(user)
    session.add(Settings(key="default_limit", value="1"))
    
    q1 = QueueType(name="Q1", is_active=True)
    q2 = QueueType(name="Q2", is_active=True)
    session.add_all([q1, q2])
    await session.flush()

    char = Character(user_id=user.id, nickname="C2", is_main=True)
    session.add(char)
    await session.commit()

    # Join Q1 (Limit 1/1)
    await join_queue(session, user.id, q1.id, char.id, is_auto=False)

    # Try Join Q2 (Should fail)
    success, msg, _ = await join_queue(session, user.id, q2.id, char.id, is_auto=False)

    assert success is False
    assert "Лимит" in msg


@pytest.mark.asyncio
async def test_leave_queue(async_test_session):
    session = async_test_session

    user = User(telegram_id=333, username="u3")
    session.add(user)
    q = QueueType(name="Q3", is_active=True)
    session.add(q)
    await session.flush()

    # Add Entry manually
    session.add(QueueEntry(user_id=user.id, queue_type_id=q.id, character_name="C3"))
    await session.commit()

    # Test Leave
    success, msg, entry = await leave_queue(session, user.id, q.id)

    assert success is True
    assert entry.character_name == "C3"

    # Verify Gone
    result = await session.execute(select(QueueEntry).filter_by(user_id=user.id, queue_type_id=q.id))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_join_queue_auto(async_test_session):
    session = async_test_session
    user = User(telegram_id=444, username="u4")
    session.add(user)
    q = QueueType(name="Q4", is_active=True)
    session.add(q)
    await session.flush()
    
    char = Character(user_id=user.id, nickname="C4", is_main=True)
    session.add(char)
    await session.commit()

    success, msg, entry = await join_queue(session, user.id, q.id, char.id, is_auto=True)

    assert success is True
    assert entry.auto_requeue is True
    assert "Авто" in msg
