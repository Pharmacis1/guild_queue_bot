import logging

import pytest

from utils import log_reward_to_sheet


@pytest.mark.asyncio
async def test_log_reward_stub(caplog):
    """
    Verifies that log_reward_to_sheet logs the correct message.
    """
    with caplog.at_level(logging.INFO):
        await log_reward_to_sheet(
            queue_name="Q1", main_nick="MainUser", char_nick="Char1", manager_name="Admin", status="UnitTest"
        )

    # Check that it logged (stub behavior)
    assert "Reward Log: Q1 | MainUser (Char1) | By: Admin | Status: UnitTest" in caplog.text

    # If it were real integration, we'd mock the gspread call here.
