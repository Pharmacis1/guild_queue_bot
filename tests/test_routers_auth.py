import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock, AsyncMock
from main import app
from database import User, Character

# ---------------------------------------------------------
# GET /login/telegram
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_login_telegram_no_bot_token():
    with patch("routers.auth.BOT_TOKEN", None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/login/telegram?id=123")
            assert response.status_code == 200
            assert "Server Config Error" in response.text

@pytest.mark.asyncio
async def test_login_telegram_invalid_hash():
    with patch("routers.auth.BOT_TOKEN", "fake_token:123"):
        with patch("routers.auth.validate_widget_auth", side_effect=ValueError("Invalid hash")):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/login/telegram?id=123&hash=bad")
                assert response.status_code == 307 or response.status_code == 302 # Redirect
                assert "error=auth_failed" in str(response.headers.get("location", ""))

@pytest.mark.asyncio
async def test_login_telegram_user_not_found(async_test_session):
    # Ensure user 123 does not exist in async_test_session
    with patch("routers.auth.BOT_TOKEN", "fake_token:123"):
        with patch("routers.auth.validate_widget_auth"):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/login/telegram?id=123&photo_url=http")
                assert "error=not_registered" in str(response.headers.get("location", ""))

@pytest.mark.asyncio
async def test_login_telegram_success(async_test_session):
    # Setup user in mock DB
    async_test_session.add(User(telegram_id=123, username="testuser"))
    await async_test_session.commit()

    with patch("routers.auth.BOT_TOKEN", "fake_token:123"):
        with patch("routers.auth.validate_widget_auth"):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.get("/login/telegram?id=123&photo_url=http")
                location = str(response.headers.get("location", ""))
                assert "error" not in location

# ---------------------------------------------------------
# POST /api/login
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_api_login_no_bot_token():
    with patch("routers.auth.BOT_TOKEN", None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/login", json={"initData": "foo"})
            assert response.status_code == 500
            assert "Config Error" in response.json()["message"]

@pytest.mark.asyncio
async def test_api_login_invalid_init_data():
    with patch("routers.auth.validate_init_data", side_effect=ValueError("Bad initData")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/login", json={"initData": "foo"})
            assert response.status_code == 403
            assert "Auth failed" in response.json()["message"]

@pytest.mark.asyncio
async def test_api_login_no_user_data():
    with patch("routers.auth.validate_init_data", return_value={"other": "data"}):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/login", json={"initData": "foo"})
            assert response.status_code == 400

@pytest.mark.asyncio
async def test_api_login_user_not_found(async_test_session):
    parsed_data = {"user": {"id": 123}}
    with patch("routers.auth.validate_init_data", return_value=parsed_data):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/login", json={"initData": "foo"})
            assert response.status_code == 403
            assert "не зарегистрированы" in response.json()["message"]

@pytest.mark.asyncio
async def test_api_login_zero_chars(async_test_session):
    # Setup user but NO characters
    async_test_session.add(User(telegram_id=123, username="testuser"))
    await async_test_session.commit()

    parsed_data = {"user": {"id": 123}}
    with patch("routers.auth.BOT_TOKEN", "fake_token:123"):
        with patch("routers.auth.validate_init_data", return_value=parsed_data):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post("/api/login", json={"initData": "foo"})
                assert response.status_code == 403
                assert "нет персонажей" in response.json()["message"]

@pytest.mark.asyncio
async def test_api_login_success(async_test_session):
    # Setup user AND character
    user = User(id=1, telegram_id=123, username="testuser")
    async_test_session.add(user)
    await async_test_session.commit()
    
    char = Character(id=1, user_id=1, nickname="Hero")
    async_test_session.add(char)
    await async_test_session.commit()

    parsed_data = {"user": {"id": 123}}
    with patch("routers.auth.BOT_TOKEN", "fake_token:123"):
        with patch("routers.auth.validate_init_data", return_value=parsed_data):
            with patch("routers.auth.get_telegram_avatar_url", new_callable=AsyncMock) as mock_ava:
                mock_ava.return_value = "http://avatar"
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    response = await ac.post("/api/login", json={"initData": "foo"})
                    assert response.status_code == 200
                    assert response.json()["message"] == "Logged in"

@pytest.mark.asyncio
async def test_api_login_exception():
    with patch("routers.auth.validate_init_data", side_effect=Exception("DB Crash")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/login", json={"initData": "foo"})
            assert response.status_code == 500

# ---------------------------------------------------------
# POST /api/login/widget
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_widget_login_no_bot_token():
    with patch("routers.auth.BOT_TOKEN", None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/login/widget", json={"id": 1, "first_name": "a", "auth_date": 1, "hash": "a"})
            assert response.status_code == 500

@pytest.mark.asyncio
async def test_widget_login_invalid_hash():
    with patch("routers.auth.validate_widget_auth", side_effect=ValueError("Bad hash")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/login/widget", json={"id": 1, "first_name": "a", "auth_date": 1, "hash": "a"})
            assert response.status_code == 403

@pytest.mark.asyncio
async def test_widget_login_user_not_found(async_test_session):
    with patch("routers.auth.BOT_TOKEN", "fake_token:123"):
        with patch("routers.auth.validate_widget_auth"):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post("/api/login/widget", json={"id": 1, "first_name": "a", "auth_date": 1, "hash": "a"})
                assert response.status_code == 403
                assert "не зарегистрированы" in response.json()["message"]

@pytest.mark.asyncio
async def test_widget_login_success(async_test_session):
    async_test_session.add(User(telegram_id=1, username="testuser"))
    await async_test_session.commit()

    with patch("routers.auth.BOT_TOKEN", "fake_token:123"):
        with patch("routers.auth.validate_widget_auth"):
            with patch("routers.auth.get_telegram_avatar_url", new_callable=AsyncMock) as mock_ava:
                mock_ava.return_value = "http://avatar"
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                    payload = {"id": 1, "first_name": "a", "auth_date": 1, "hash": "a"}
                    response = await ac.post("/api/login/widget", json=payload)
                    assert response.status_code == 200

@pytest.mark.asyncio
async def test_widget_login_exception():
    with patch("routers.auth.validate_widget_auth", side_effect=Exception("DB Crash")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post("/api/login/widget", json={"id": 1, "first_name": "a", "auth_date": 1, "hash": "a"})
            assert response.status_code == 500

# ---------------------------------------------------------
# GET, POST /logout
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_post():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/logout")
        assert response.status_code == 200
        assert response.json()["message"] == "Logged out"

@pytest.mark.asyncio
async def test_logout_get():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Will redirect
        response = await ac.get("/logout")
        # AsyncClient follows redirects by default or returns the 307. 
        # TestClient behavior was with allow_redirects=False.
        assert response.status_code == 307 or response.status_code == 302
        assert response.headers["location"] == "/"
