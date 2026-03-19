import pytest
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import User, Character, Player, QueueEntry, QueueType, PartyMember, ConstantParty
from helpers import get_menu_text


@pytest.mark.asyncio
async def test_get_menu_text_with_cp_named(async_test_session):
    """Test get_menu_text includes named CP info correctly"""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.commit()

    char = Character(user_id=user.id, nickname="TestChar", is_main=True)
    async_test_session.add(char)
    await async_test_session.commit()

    player = Player(role_id=123, nickname="TestChar", in_clan=1, user_id=user.id)
    async_test_session.add(player)
    await async_test_session.commit()

    cp = ConstantParty(name="Elite Squad", color="#FF0000")
    async_test_session.add(cp)
    await async_test_session.commit()

    pm = PartyMember(party_id=cp.id, player_role_id=player.role_id, is_leader=False)
    async_test_session.add(pm)
    await async_test_session.commit()
    await async_test_session.refresh(user, ['characters'])

    # Test output
    text, all_out = await get_menu_text(async_test_session, user)
    assert "Elite Squad" in text
    assert "КП: «Elite Squad»" in text


@pytest.mark.asyncio
async def test_get_menu_text_with_cp_no_name(async_test_session):
    """Test get_menu_text includes CP leader's name when CP has no name"""
    user = User(telegram_id=123456789, username="test_user")
    leader_user = User(telegram_id=987654321, username="leader_user")
    async_test_session.add_all([user, leader_user])
    await async_test_session.commit()

    char = Character(user_id=user.id, nickname="TestChar", is_main=True)
    leader_char = Character(user_id=leader_user.id, nickname="LeaderChar", is_main=True)
    async_test_session.add_all([char, leader_char])
    await async_test_session.commit()

    player = Player(role_id=123, nickname="TestChar", in_clan=1, user_id=user.id)
    leader_player = Player(role_id=456, nickname="LeaderChar", in_clan=1, user_id=leader_user.id)
    async_test_session.add_all([player, leader_player])
    await async_test_session.commit()

    cp = ConstantParty(name=None, color="#00FF00")
    async_test_session.add(cp)
    await async_test_session.commit()

    pm = PartyMember(party_id=cp.id, player_role_id=player.role_id, is_leader=False)
    leader_pm = PartyMember(party_id=cp.id, player_role_id=leader_player.role_id, is_leader=True)
    async_test_session.add_all([pm, leader_pm])
    await async_test_session.commit()
    await async_test_session.refresh(user, ['characters'])

    text, all_out = await get_menu_text(async_test_session, user)
    assert "КП: LeaderChar" in text
