import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy import select

from main import app
from database import FaqTopic, FaqMessage, Settings, User

# ---------------------------------------------------------
# Fixtures & Mocks
# ---------------------------------------------------------

@pytest.fixture
def mock_master_user():
    # Helper to mock get_current_user as master
    with patch("routers.api_dashboard.get_current_user") as mock_u:
        user = MagicMock()
        user.is_master = True
        user.id = 1
        user.telegram_id = 123
        mock_u.return_value = user
        yield mock_u

@pytest.fixture
def mock_ai_helper():
    with patch("logic.ai_helper.get_ai_helper") as mock_ai:
        ai = AsyncMock()
        mock_ai.return_value = ai
        yield ai

# ---------------------------------------------------------
# Admin Settings
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_settings_get(mock_master_user, async_test_session):
    # Setup some settings
    async_test_session.add(Settings(key="public_log_enabled", value="true"))
    async_test_session.add(Settings(key="verification_code", value="TESTCODE"))
    await async_test_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/dashboard/admin/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["public_log_enabled"] is True
        assert data["verification_code"] == "TESTCODE"

@pytest.mark.asyncio
async def test_admin_settings_post(mock_master_user, async_test_session):
    payload = {
        "public_log_enabled": False,
        "public_log_channel_id": "-123456",
        "public_log_thread_id": "789",
        "verification_code": "NEWCODE"
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/dashboard/admin/settings", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    # Verify in DB
    from database import get_setting
    val = await get_setting(async_test_session, "verification_code")
    assert val == "NEWCODE"

# ---------------------------------------------------------
# Backups
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_list_backups(mock_master_user):
    with patch("os.path.exists", return_value=True), \
         patch("glob.glob", return_value=["guild_bot_2024.db"]), \
         patch("os.path.getsize", return_value=1024*1024), \
         patch("os.path.getmtime", return_value=1700000000.0):
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get("/api/dashboard/admin/backups")
            assert response.status_code == 200
            assert len(response.json()) == 1
            assert response.json()[0]["name"] == "guild_bot_2024.db"

# ---------------------------------------------------------
# FAQ & AI
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_faq_crud_lifecycle(mock_master_user, async_test_session, mock_ai_helper):
    mock_ai_helper.embed_text.return_value = [0.1, 0.2]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Create Topic
        topic_payload = {
            "topic": "Test FAQ",
            "initial_messages": [{"text": "Hello FAQ"}]
        }
        res_create = await ac.post("/api/dashboard/admin/faq", json=topic_payload)
        assert res_create.status_code == 200
        topic_id = res_create.json()["id"]
        assert res_create.json()["topic"] == "Test FAQ"

        # 2. List Topics
        res_list = await ac.get("/api/dashboard/admin/faq")
        assert len(res_list.json()) >= 1

        # 3. Add Message
        msg_payload = {"text": "Extra info", "photo_id": None}
        res_msg = await ac.post(f"/api/dashboard/admin/faq/{topic_id}/messages", json=msg_payload)
        assert res_msg.status_code == 200

        # 4. Get Topic Details
        res_get = await ac.get(f"/api/dashboard/admin/faq/{topic_id}")
        assert res_get.status_code == 200
        assert len(res_get.json()["messages"]) == 2

        # 5. Delete Message
        msg_id_to_del = res_get.json()["messages"][1]["id"]
        res_del_msg = await ac.delete(f"/api/dashboard/admin/faq/messages/{msg_id_to_del}")
        assert res_del_msg.status_code == 200

        # 6. Update Topic name
        res_update = await ac.put(f"/api/dashboard/admin/faq/{topic_id}", json={"topic": "Updated FAQ"})
        assert res_update.status_code == 200

        # 7. Delete Topic
        res_del_topic = await ac.delete(f"/api/dashboard/admin/faq/{topic_id}")
        assert res_del_topic.status_code == 200

@pytest.mark.asyncio
async def test_faq_ai_ask(mock_master_user, async_test_session, mock_ai_helper):
    # Setup a topic with embedding
    topic = FaqTopic(topic="Gemini Topic", embedding="[0.1, 0.2]")
    msg = FaqMessage(topic=topic, text="The answer is 42", order_index=1)
    async_test_session.add(topic)
    async_test_session.add(msg)
    await async_test_session.commit()

    mock_ai_helper.find_relevant_topics.return_value = [topic]
    mock_ai_helper.get_answer.return_value = "AI Answer: 42"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res_ask = await ac.post("/api/dashboard/admin/faq/ask", json={"question": "What is the answer?"})
        assert res_ask.status_code == 200
        assert res_ask.json()["answer"] == "AI Answer: 42"
