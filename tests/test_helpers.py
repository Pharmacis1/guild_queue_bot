import pytest
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import User, Character, Player, QueueEntry, QueueType, PartyMember, ConstantParty
from helpers import get_menu_text


@pytest.fixture
def sync_test_session(test_db_session):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{test_db_session}")
    Session = sessionmaker(bind=engine)
    session = Session()

    with patch("database.session", session), patch("helpers.session", session):
        yield session

    session.close()


def test_get_menu_text_with_cp_named(sync_test_session):
    """Test get_menu_text includes named CP info correctly"""
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    char = Character(user_id=user.id, nickname="TestChar", is_main=True)
    sync_test_session.add(char)
    sync_test_session.commit()

    player = Player(role_id=123, nickname="TestChar", in_clan=1, user_id=user.id)
    sync_test_session.add(player)
    sync_test_session.commit()

    cp = ConstantParty(name="Elite Squad", color="#FF0000")
    sync_test_session.add(cp)
    sync_test_session.commit()

    pm = PartyMember(party_id=cp.id, player_role_id=player.role_id, is_leader=False)
    sync_test_session.add(pm)
    sync_test_session.commit()

    # Test output
    text, all_out = get_menu_text(user)
    assert "Elite Squad" in text
    assert "КП: «Elite Squad»" in text


def test_get_menu_text_with_cp_no_name(sync_test_session):
    """Test get_menu_text includes CP leader's name when CP has no name"""
    user = User(telegram_id=123456789, username="test_user")
    leader_user = User(telegram_id=987654321, username="leader_user")
    sync_test_session.add_all([user, leader_user])
    sync_test_session.commit()

    char = Character(user_id=user.id, nickname="TestChar", is_main=True)
    leader_char = Character(user_id=leader_user.id, nickname="LeaderChar", is_main=True)
    sync_test_session.add_all([char, leader_char])
    sync_test_session.commit()

    player = Player(role_id=123, nickname="TestChar", in_clan=1, user_id=user.id)
    leader_player = Player(role_id=456, nickname="LeaderChar", in_clan=1, user_id=leader_user.id)
    sync_test_session.add_all([player, leader_player])
    sync_test_session.commit()

    cp = ConstantParty(name=None, color="#00FF00")
    sync_test_session.add(cp)
    sync_test_session.commit()

    pm = PartyMember(party_id=cp.id, player_role_id=player.role_id, is_leader=False)
    leader_pm = PartyMember(party_id=cp.id, player_role_id=leader_player.role_id, is_leader=True)
    sync_test_session.add_all([pm, leader_pm])
    sync_test_session.commit()

    text, all_out = get_menu_text(user)
    assert "КП: LeaderChar" in text
