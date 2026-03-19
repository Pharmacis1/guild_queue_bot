import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from database import Base, User, Character, QueueType, QueueEntry, Settings, Player

from logic.queue_ops import join_queue, leave_queue, get_admin_queue_entries, get_admin_queue_count

# --- Tests ---

@pytest.mark.asyncio
async def test_join_queue_success(async_test_session):
    # Setup
    user = User(telegram_id=123, username="test_u")
    char = Character(nickname="TestChar", is_main=True, user=user)
    qt = QueueType(name="TestQ", is_active=True)
    async_test_session.add_all([user, char, qt])
    await async_test_session.commit()
    
    # Execute
    success, msg, entry = await join_queue(async_test_session, user.id, qt.id, char.id, True)
    
    # Assert
    assert success is True
    assert "Записан: TestChar" in msg
    assert entry is not None
    assert entry.auto_requeue is True
    assert entry.character_name == "TestChar"
    
    result = await async_test_session.execute(select(func.count(QueueEntry.id)))
    assert result.scalar() == 1

@pytest.mark.asyncio
async def test_join_queue_ordering(async_test_session):
    u1 = User(telegram_id=101, username="u1", personal_limit=5)
    u2 = User(telegram_id=102, username="u2", personal_limit=5)
    c1 = Character(nickname="Char1", is_main=True, user=u1)
    c2 = Character(nickname="Char2", is_main=True, user=u2)
    qt = QueueType(name="OrderTestQ", is_active=True)
    
    async_test_session.add_all([u1, u2, c1, c2, qt])
    await async_test_session.commit()
    
    success1, _, entry1 = await join_queue(async_test_session, u1.id, qt.id, c1.id, True)
    assert success1 is True
    assert entry1.position == 1
    
    success2, _, entry2 = await join_queue(async_test_session, u2.id, qt.id, c2.id, True)
    assert success2 is True
    assert entry2.position == 2

@pytest.mark.asyncio
async def test_join_queue_invalid_char(async_test_session):
    user = User(telegram_id=123, username="test_u")
    qt = QueueType(name="TestQ", is_active=True)
    async_test_session.add_all([user, qt])
    await async_test_session.commit()
    
    success, msg, entry = await join_queue(async_test_session, user.id, qt.id, 999, False)
    assert success is False
    assert "Ошибка чара" in msg
    assert entry is None

@pytest.mark.asyncio
async def test_join_queue_already_in(async_test_session):
    user = User(telegram_id=123, username="test_u")
    char = Character(nickname="TestChar", is_main=True, user=user)
    qt = QueueType(name="TestQ", is_active=True)
    async_test_session.add_all([user, char, qt])
    await async_test_session.commit()
    
    async_test_session.add(QueueEntry(queue_type_id=qt.id, user_id=user.id, character_name="TestChar"))
    await async_test_session.commit()
    
    success, msg, entry = await join_queue(async_test_session, user.id, qt.id, char.id, True)
    assert success is False
    assert "уже в очереди" in msg
    assert entry is None
    
    result = await async_test_session.execute(select(func.count(QueueEntry.id)))
    assert result.scalar() == 1

@pytest.mark.asyncio
async def test_join_queue_limit_reached(async_test_session):
    user = User(telegram_id=123, username="test_u", personal_limit=1)
    char = Character(nickname="TestChar", is_main=True, user=user)
    qt1 = QueueType(name="TestQ1", is_active=True)
    qt2 = QueueType(name="TestQ2", is_active=True)
    async_test_session.add_all([user, char, qt1, qt2])
    await async_test_session.commit()
    
    # Fill limit
    async_test_session.add(QueueEntry(queue_type_id=qt1.id, user_id=user.id, character_name="TestChar"))
    await async_test_session.commit()
    
    success, msg, entry = await join_queue(async_test_session, user.id, qt2.id, char.id, True)
    assert success is False
    assert "Лимит записей исчерпан" in msg
    assert entry is None

@pytest.mark.asyncio
async def test_join_queue_limit_fallback(async_test_session):
    # Test when personal_limit is None and default_limit setting is missing.
    user = User(telegram_id=123, username="test_u") # no limit
    char = Character(nickname="TestChar", is_main=True, user=user)
    qt1 = QueueType(name="TestQ1", is_active=True)
    qt2 = QueueType(name="TestQ2", is_active=True)
    async_test_session.add_all([user, char, qt1, qt2])
    await async_test_session.commit()
    
    # Fill default fallback limit (1)
    async_test_session.add(QueueEntry(queue_type_id=qt1.id, user_id=user.id, character_name="TestChar"))
    await async_test_session.commit()
    
    # This should fail because limit is 1 by default fallback
    success, msg, entry = await join_queue(async_test_session, user.id, qt2.id, char.id, True)
    assert success is False
    assert "Лимит" in msg
    assert entry is None

@pytest.mark.asyncio
async def test_leave_queue_success(async_test_session):
    user = User(telegram_id=123, username="test_u")
    qt = QueueType(name="TestQ", is_active=True)
    async_test_session.add_all([user, qt])
    await async_test_session.commit()
    
    entry_row = QueueEntry(queue_type_id=qt.id, user_id=user.id, character_name="TestChar")
    async_test_session.add(entry_row)
    await async_test_session.commit()
    
    success, msg, deleted_entry = await leave_queue(async_test_session, user.id, qt.id)
    assert success is True
    assert "Вы вышли" in msg
    assert deleted_entry is not None
    assert deleted_entry.character_name == "TestChar"
    
    result = await async_test_session.execute(select(func.count(QueueEntry.id)))
    assert result.scalar() == 0

@pytest.mark.asyncio
async def test_leave_queue_not_found(async_test_session):
    user = User(telegram_id=123, username="test_u")
    qt = QueueType(name="TestQ", is_active=True)
    async_test_session.add_all([user, qt])
    await async_test_session.commit()
    
    success, msg, deleted_entry = await leave_queue(async_test_session, user.id, qt.id)
    assert success is False
    assert "Уже вышли" in msg
    assert deleted_entry is None

@pytest.mark.asyncio
async def test_get_admin_queue_entries_and_count(async_test_session):
    user = User(telegram_id=123, username="test_u")
    qt = QueueType(name="TestQ", is_active=True)
    async_test_session.add_all([user, qt])
    await async_test_session.commit()
    
    # Entry 1: In clan
    entry1 = QueueEntry(queue_type_id=qt.id, user_id=user.id, character_name="PlayerInClan")
    player1 = Player(role_id=1, nickname="PlayerInClan", in_clan=1)
    
    # Entry 2: Not in clan
    entry2 = QueueEntry(queue_type_id=qt.id, user_id=user.id, character_name="PlayerNotInClan")
    player2 = Player(role_id=2, nickname="PlayerNotInClan", in_clan=0)
    
    # Entry 3: No player record (should be included by IS NULL logic)
    entry3 = QueueEntry(queue_type_id=qt.id, user_id=user.id, character_name="UnknownPlayer")
    
    async_test_session.add_all([entry1, player1, entry2, player2, entry3])
    await async_test_session.commit()
    
    entries = await get_admin_queue_entries(async_test_session, qt.id)
    count = await get_admin_queue_count(async_test_session, qt.id)
    
    assert len(entries) == 2
    assert count == 2
    
    chars = [e.character_name for e in entries]
    assert "PlayerInClan" in chars
    assert "UnknownPlayer" in chars
    assert "PlayerNotInClan" not in chars
