import pytest

from database import Player, QueueEntry, QueueType, User
from logic.queue_ops import get_admin_queue_count, get_admin_queue_entries, join_queue, leave_queue
from logic.reward_ops import issue_reward, warn_user


@pytest.fixture
def sync_test_session(test_db_session):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{test_db_session}")
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def setup_admin_data(session):
    # Master
    master = User(telegram_id=999, username="master_user", is_master=True)
    session.add(master)

    # User
    user = User(telegram_id=111, username="player")
    session.add(user)

    # Queue
    q = QueueType(name="AdminQ", is_active=True)
    session.add(q)

    session.commit()
    return master, user, q


def test_issue_reward_normal(sync_test_session):
    session = sync_test_session
    master, user, q = setup_admin_data(session)

    # Entry (Manual)
    entry = QueueEntry(user_id=user.id, queue_type_id=q.id, character_name="P1", auto_requeue=False)
    session.add(entry)
    session.commit()

    success, msg, hist = issue_reward(session, entry.id, master.username)

    assert success is True
    assert "Ушел" in msg
    assert hist.user_id == user.id
    assert hist.issued_by == "master_user"

    # Check Entry Gone
    assert session.query(QueueEntry).filter_by(id=entry.id).first() is None
    # Check No Requeue
    assert session.query(QueueEntry).filter_by(user_id=user.id, queue_type_id=q.id).count() == 0


def test_issue_reward_auto(sync_test_session):
    session = sync_test_session
    master, user, q = setup_admin_data(session)

    # Entry (Auto)
    entry = QueueEntry(user_id=user.id, queue_type_id=q.id, character_name="P2", auto_requeue=True)
    session.add(entry)
    session.commit()

    original_id = entry.id
    success, msg, hist = issue_reward(session, original_id, master.username)

    assert success is True
    assert "Перезаписан" in msg

    # Check Old Entry Gone
    assert session.query(QueueEntry).filter_by(id=original_id).first() is None

    # Check New Entry Exists
    new_entry = session.query(QueueEntry).filter_by(user_id=user.id, queue_type_id=q.id).first()
    assert new_entry is not None
    assert new_entry.id != original_id
    assert new_entry.auto_requeue is True


def test_warn_user(sync_test_session):
    session = sync_test_session
    master, user, q = setup_admin_data(session)

    entry = QueueEntry(user_id=user.id, queue_type_id=q.id, character_name="P3")
    session.add(entry)
    session.commit()

    success, msg, hist = warn_user(session, entry.id, master.username)

    assert success is True
    assert "Предупреждение" in msg
    assert hist.record_type == "warning"
    assert hist.user_id == user.id

    # Entry should REMAIN (Warn doesn't remove)
    assert session.query(QueueEntry).filter_by(id=entry.id).first() is not None


def test_get_admin_queue_logic(sync_test_session):
    session = sync_test_session
    master, user, q = setup_admin_data(session)

    # 1. Add 3 entries
    # - P1: Not in Player table (should be visible)
    # - P2: in Player table AND in_clan=1 (should be visible)
    # - P3: in Player table AND in_clan=0 (should be HIDDEN)
    
    e1 = QueueEntry(user_id=user.id, queue_type_id=q.id, character_name="P1")
    e2 = QueueEntry(user_id=user.id, queue_type_id=q.id, character_name="P2")
    e3 = QueueEntry(user_id=user.id, queue_type_id=q.id, character_name="P3")
    session.add_all([e1, e2, e3])
    
    p2 = Player(nickname="P2", in_clan=1)
    p3 = Player(nickname="P3", in_clan=0)
    session.add_all([p2, p3])
    
    session.commit()

    # 2. Test Count
    count = get_admin_queue_count(session, q.id)
    assert count == 2  # P1 and P2, but not P3

    # 3. Test Entries
    entries = get_admin_queue_entries(session, q.id)
    assert len(entries) == 2
    nicks = [e.character_name for e in entries]
    assert "P1" in nicks
    assert "P2" in nicks
    assert "P3" not in nicks
