import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, User, Character, QueueType, QueueEntry, Settings, Player

from logic.queue_ops import join_queue, leave_queue, get_admin_queue_entries, get_admin_queue_count

# --- Fixtures for Sync DB ---
@pytest.fixture(scope="function")
def sync_db_engine():
    """Create a temporary in-memory database and tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture(scope="function")
def sync_test_session(sync_db_engine):
    """Session for the temporary memory database."""
    Session = sessionmaker(bind=sync_db_engine)
    session = Session()
    yield session
    session.close()

# --- Tests ---

def test_join_queue_success(sync_test_session):
    # Setup
    user = User(telegram_id=123, username="test_u")
    char = Character(nickname="TestChar", is_main=True, user=user)
    qt = QueueType(name="TestQ", is_active=True)
    sync_test_session.add_all([user, char, qt])
    sync_test_session.commit()
    
    # Execute
    success, msg, entry = join_queue(sync_test_session, user.id, qt.id, char.id, True)
    
    # Assert
    assert success is True
    assert "Записан: TestChar" in msg
    assert entry is not None
    assert entry.auto_requeue is True
    assert entry.character_name == "TestChar"
    assert sync_test_session.query(QueueEntry).count() == 1

def test_join_queue_invalid_char(sync_test_session):
    user = User(telegram_id=123, username="test_u")
    qt = QueueType(name="TestQ", is_active=True)
    sync_test_session.add_all([user, qt])
    sync_test_session.commit()
    
    success, msg, entry = join_queue(sync_test_session, user.id, qt.id, 999, False)
    assert success is False
    assert "Ошибка чара" in msg
    assert entry is None

def test_join_queue_already_in(sync_test_session):
    user = User(telegram_id=123, username="test_u")
    char = Character(nickname="TestChar", is_main=True, user=user)
    qt = QueueType(name="TestQ", is_active=True)
    sync_test_session.add_all([user, char, qt])
    sync_test_session.commit()
    
    sync_test_session.add(QueueEntry(queue_type_id=qt.id, user_id=user.id, character_name="TestChar"))
    sync_test_session.commit()
    
    success, msg, entry = join_queue(sync_test_session, user.id, qt.id, char.id, True)
    assert success is False
    assert "уже в очереди" in msg
    assert entry is None
    assert sync_test_session.query(QueueEntry).count() == 1

def test_join_queue_limit_reached(sync_test_session):
    user = User(telegram_id=123, username="test_u", personal_limit=1)
    char = Character(nickname="TestChar", is_main=True, user=user)
    qt1 = QueueType(name="TestQ1", is_active=True)
    qt2 = QueueType(name="TestQ2", is_active=True)
    sync_test_session.add_all([user, char, qt1, qt2])
    sync_test_session.commit()
    
    # Fill limit
    sync_test_session.add(QueueEntry(queue_type_id=qt1.id, user_id=user.id, character_name="TestChar"))
    sync_test_session.commit()
    
    success, msg, entry = join_queue(sync_test_session, user.id, qt2.id, char.id, True)
    assert success is False
    assert "Лимит записей исчерпан" in msg
    assert entry is None

def test_join_queue_limit_fallback(sync_test_session):
    # Test when personal_limit is None and default_limit setting is missing.
    user = User(telegram_id=123, username="test_u") # no limit
    char = Character(nickname="TestChar", is_main=True, user=user)
    qt1 = QueueType(name="TestQ1", is_active=True)
    qt2 = QueueType(name="TestQ2", is_active=True)
    sync_test_session.add_all([user, char, qt1, qt2])
    sync_test_session.commit()
    
    # Fill default fallback limit (1)
    sync_test_session.add(QueueEntry(queue_type_id=qt1.id, user_id=user.id, character_name="TestChar"))
    sync_test_session.commit()
    
    # This should fail because limit is 1 by default fallback
    success, msg, entry = join_queue(sync_test_session, user.id, qt2.id, char.id, True)
    assert success is False
    assert "Лимит" in msg
    assert entry is None

def test_leave_queue_success(sync_test_session):
    user = User(telegram_id=123, username="test_u")
    qt = QueueType(name="TestQ", is_active=True)
    sync_test_session.add_all([user, qt])
    sync_test_session.commit()
    
    entry_row = QueueEntry(queue_type_id=qt.id, user_id=user.id, character_name="TestChar")
    sync_test_session.add(entry_row)
    sync_test_session.commit()
    
    success, msg, deleted_entry = leave_queue(sync_test_session, user.id, qt.id)
    assert success is True
    assert "Вы вышли" in msg
    assert deleted_entry is not None
    assert deleted_entry.character_name == "TestChar"
    assert sync_test_session.query(QueueEntry).count() == 0

def test_leave_queue_not_found(sync_test_session):
    user = User(telegram_id=123, username="test_u")
    qt = QueueType(name="TestQ", is_active=True)
    sync_test_session.add_all([user, qt])
    sync_test_session.commit()
    
    success, msg, deleted_entry = leave_queue(sync_test_session, user.id, qt.id)
    assert success is False
    assert "Уже вышли" in msg
    assert deleted_entry is None

def test_get_admin_queue_entries_and_count(sync_test_session):
    user = User(telegram_id=123, username="test_u")
    qt = QueueType(name="TestQ", is_active=True)
    sync_test_session.add_all([user, qt])
    sync_test_session.commit()
    
    # Entry 1: In clan
    entry1 = QueueEntry(queue_type_id=qt.id, user_id=user.id, character_name="PlayerInClan")
    player1 = Player(role_id=1, nickname="PlayerInClan", in_clan=1)
    
    # Entry 2: Not in clan
    entry2 = QueueEntry(queue_type_id=qt.id, user_id=user.id, character_name="PlayerNotInClan")
    player2 = Player(role_id=2, nickname="PlayerNotInClan", in_clan=0)
    
    # Entry 3: No player record (should be included by IS NULL logic)
    entry3 = QueueEntry(queue_type_id=qt.id, user_id=user.id, character_name="UnknownPlayer")
    
    sync_test_session.add_all([entry1, player1, entry2, player2, entry3])
    sync_test_session.commit()
    
    entries = get_admin_queue_entries(sync_test_session, qt.id)
    count = get_admin_queue_count(sync_test_session, qt.id)
    
    assert len(entries) == 2
    assert count == 2
    
    chars = [e.character_name for e in entries]
    assert "PlayerInClan" in chars
    assert "UnknownPlayer" in chars
    assert "PlayerNotInClan" not in chars
