import pytest

from database import QueueEntry, QueueType, User
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
