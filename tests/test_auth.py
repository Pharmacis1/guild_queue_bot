
import pytest

from auth_helper import validate_init_data

# Mock BOT_TOKEN for testing if the function accepts it as arg, or we set env
MOCK_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

# Sample Init Data (from Telegram docs or constructed)
# query_id=...&user=...&auth_date=...&hash=...
# We need a valid hash to pass validation, which is hard to generate without the secret key logic duplication.
# So we might test failure cases or basic structure if we can't easily generate valid hash.
# OR we rely on the fact that we can generate a signature if we know the algorithm.

def test_validate_init_data_invalid():
    """Test that invalid data raises ValueError"""
    invalid_data = "query_id=123&hash=fake"
    with pytest.raises(ValueError):
        validate_init_data(invalid_data, MOCK_TOKEN)

def test_validate_init_data_empty():
    with pytest.raises(ValueError):
        validate_init_data("", MOCK_TOKEN)
