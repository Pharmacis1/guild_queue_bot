import pytest
import datetime
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

from main import app
from routers.observer import init_browser, close_browser
from database import ObserverCache, get_msk_now

# ---------------------------------------------------------
# Test browser startup and shutdown
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_init_browser_success():
    # Force globals to None just in case
    import routers.observer
    routers.observer.BROWSER_INSTANCE = None
    routers.observer.CONTEXT_INSTANCE = None
    routers.observer.PLAYWRIGHT_INSTANCE = None
    
    mock_pw = AsyncMock()
    mock_pw_context = AsyncMock()
    mock_pw.chromium.launch.return_value.new_context.return_value = mock_pw_context
    
    with patch("routers.observer.async_playwright", return_value=AsyncMock(start=AsyncMock(return_value=mock_pw))):
        with patch("os.path.exists", return_value=True):
            await init_browser()
            assert routers.observer.BROWSER_INSTANCE is not None
            assert routers.observer.CONTEXT_INSTANCE is not None
        
        # Calling again does nothing
        await init_browser()

@pytest.mark.asyncio
async def test_init_browser_fail():
    import routers.observer
    routers.observer.BROWSER_INSTANCE = None
    
    with patch("routers.observer.async_playwright", side_effect=Exception("Failed to launch")):
        await init_browser()
        assert routers.observer.BROWSER_INSTANCE is None

@pytest.mark.asyncio
async def test_close_browser():
    import routers.observer
    
    mock_browser = AsyncMock()
    mock_pw = AsyncMock()
    routers.observer.BROWSER_INSTANCE = mock_browser
    routers.observer.PLAYWRIGHT_INSTANCE = mock_pw
    
    await close_browser()
    assert mock_browser.close.call_count == 1
    assert mock_pw.stop.call_count == 1

@pytest.mark.asyncio
async def test_api_observer_stats():
    import routers.observer
    routers.observer.BROWSER_INSTANCE = "Browser"
    routers.observer.CONTEXT_INSTANCE = "Context"
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/observer_stats")
        assert response.status_code == 200
        assert response.json()["browser_active"] == True
        assert response.json()["context_active"] == True

# ---------------------------------------------------------
# Test /api/observer/{role_id}
# ---------------------------------------------------------

@pytest.mark.asyncio
async def test_observer_missing_role_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/observer/0")
        assert response.status_code == 400

@pytest.mark.asyncio
async def test_observer_cache_hit(async_test_session):
    # Date within 1 hour
    now = get_msk_now()
    recent_date = now - datetime.timedelta(minutes=30)
    
    cache = ObserverCache(role_id=123987, html_content="cached_html", updated_at=recent_date)
    async_test_session.add(cache)
    await async_test_session.commit()
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/observer/123987")
        assert response.status_code == 200
        assert response.json()["source"] == "cache"
        assert response.json()["html"] == "cached_html"

@pytest.mark.asyncio
async def test_observer_cache_miss_scrape_uninitialized(async_test_session):
    import routers.observer
    routers.observer.CONTEXT_INSTANCE = None # Make it try to init
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("routers.observer.init_browser", new_callable=AsyncMock) as mock_init:
            # Mocking init_browser to NOT initialize CONTEXT_INSTANCE triggers 500
            response = await client.get("/api/observer/123987")
            assert response.status_code == 500

@pytest.mark.asyncio
async def test_observer_scrape_page_404(async_test_session):
    import routers.observer
    
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock(side_effect=Exception("Timeout"))
    mock_page.title = AsyncMock(return_value="404 Error")
    mock_page.close = AsyncMock()
    
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    
    routers.observer.CONTEXT_INSTANCE = mock_context
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/observer/123987")
        assert response.status_code == 200
        assert response.json()["status"] == "error"
        assert "not found" in response.json()["message"]

@pytest.mark.asyncio
async def test_observer_scrape_page_auth(async_test_session):
    import routers.observer
    
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.title = AsyncMock(return_value="Авторизация required")
    mock_page.close = AsyncMock()
    
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    
    routers.observer.CONTEXT_INSTANCE = mock_context
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/observer/123987")
        assert response.status_code == 200
        assert response.json()["status"] == "error"
        assert "requires login" in response.json()["message"]

@pytest.mark.asyncio
async def test_observer_scrape_success(async_test_session):
    import routers.observer
    
    mock_element = AsyncMock()
    mock_element.evaluate = AsyncMock(return_value='<div class="player-equipment"></div>')
    
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.title = AsyncMock(return_value="Player Profile")
    mock_page.wait_for_selector = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=["style.css"]) # CSS links
    mock_page.query_selector = AsyncMock(return_value=mock_element)
    mock_page.close = AsyncMock()
    
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    
    routers.observer.CONTEXT_INSTANCE = mock_context
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/observer/123987")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert "source" in response.json()
        assert response.json()["source"] == "live"
        
        html = response.json()["html"]
        assert "style.css" in html
        
        # Verify it was saved to cache
        from sqlalchemy import select
        result = await async_test_session.execute(select(ObserverCache).filter_by(role_id=123987))
        cache = result.scalar_one_or_none()
        assert cache is not None
        assert "style.css" in cache.html_content
