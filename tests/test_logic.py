import pytest

from logic.helpers import is_newcomer


@pytest.mark.parametrize(
    "days_offset, expected",
    [
        (1, True),   # Joined 1 day ago -> Newcomer
        (5, True),   # Joined 5 days ago -> Newcomer
        (13, True),  # Joined 13 days ago -> Newcomer
        (15, False), # Joined 15 days ago -> NOT Newcomer
        (30, False), # Joined 30 days ago -> NOT Newcomer
    ],
)
def test_newcomer_logic_shared(days_offset, expected):
    from datetime import datetime, timedelta
    
    # Calculate join date based on real "now"
    join_dt = datetime.now() - timedelta(days=days_offset)
    join_date_str = join_dt.strftime("%Y-%m-%d")
    
    # Mock map
    role_id = 1
    m = {1: join_date_str}
    
    # The current_date parameter in is_newcomer is ignored now, 
    # but we pass None or something just to match signature if needed.
    assert is_newcomer(role_id, m) == expected
