import pytest

from logic.helpers import is_newcomer


@pytest.mark.parametrize(
    "join_date, current_date, expected",
    [
        ("2023-01-01", "2023-01-02", True),  # Joined yesterday (assuming logic is relative to ref)
        # Wait, the logic is: (ref_monday - join_dt).days < 7
        # If ref is 2023-01-02 (Monday), ref_monday is 2023-01-02.
        # Join 2023-01-01 (Sunday). (02 - 01) = 1 day. < 7? Yes.
        # If Join 2022-12-20. (02 - Dec 20) = 13 days. > 7. False.
        ("2022-12-20", "2023-01-02", False),
    ],
)
def test_newcomer_logic_shared(join_date, current_date, expected):
    # Mock map
    role_id = 1
    m = {1: join_date}
    assert is_newcomer(role_id, m, current_date) == expected
