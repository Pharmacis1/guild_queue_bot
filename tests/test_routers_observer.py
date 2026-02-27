import pytest
import datetime
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient
from main import app
from routers.observer import router, init_browser, close_browser

client = TestClient(app)

# ---------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------

class MockCursor:
    def __init__(self, fetchall_data=None, fetchone_data=None):
        self.fetchall_data = fetchall_data
        self.fetchone_data = fetchone_data
    
    def __await__(self):
        async def _ret():
            return self
        return _ret().__await__()
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc, tb):
        pass
        
    async def fetchall(self):
        return self.fetchall_data
        
    async def fetchone(self):
        return self.fetchone_data

class MockConnection:
    def __init__(self, fetchall_data=None, fetchone_data=None):
        self.fetchall_data = fetchall_data
        self.fetchone_data = fetchone_data
        
    def __await__(self):
        async def _ret():
            return self
        return _ret().__await__()
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc, tb):
        pass
        
    def execute(self, query, *args):
        return MockCursor(self.fetchall_data, self.fetchone_data)
        
    async def commit(self):
        pass

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

def test_api_observer_stats():
    import routers.observer
    routers.observer.BROWSER_INSTANCE = "Browser"
    routers.observer.CONTEXT_INSTANCE = "Context"
    response = client.get("/api/observer_stats")
    assert response.status_code == 200
    assert response.json()["browser_active"] == True
    assert response.json()["context_active"] == True

# ---------------------------------------------------------
# Test /api/observer/{role_id}
# ---------------------------------------------------------

def test_observer_missing_role_id():
    response = client.get("/api/observer/0") # assuming 0 triggers missing role_id condition if int -> bool check
    assert response.status_code == 400

def test_observer_cache_hit():
    # Date within 1 hour
    recent_date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=("cached_html", recent_date_str))):
        response = client.get("/api/observer/123987")
        assert response.status_code == 200
        assert response.json()["source"] == "cache"
        assert response.json()["html"] == "cached_html"

def test_observer_cache_hit_ms():
    recent_date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
    
    with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=("cached_html", recent_date_str))):
        response = client.get("/api/observer/123987")
        assert response.status_code == 200
        assert response.json()["source"] == "cache"

def test_observer_cache_miss_scrape_uninitialized():
    old_date_str = (datetime.datetime.utcnow() - datetime.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    
    import routers.observer
    routers.observer.CONTEXT_INSTANCE = None # Make it try to init
    
    with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=("stale_html", old_date_str))):
        with patch("routers.observer.init_browser", new_callable=AsyncMock) as mock_init:
            response = client.get("/api/observer/123987")
            assert response.status_code == 500

def test_observer_scrape_page_404():
    import routers.observer
    
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock(side_effect=Exception("Timeout"))
    mock_page.title = AsyncMock(return_value="404 Error")
    mock_page.close = AsyncMock()
    
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    
    routers.observer.CONTEXT_INSTANCE = mock_context
    
    with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=None)):
        response = client.get("/api/observer/123987")
        assert response.status_code == 200
        assert response.json()["status"] == "error"
        assert "404" in mock_page.title.return_value

def test_observer_scrape_page_auth():
    import routers.observer
    
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.title = AsyncMock(return_value="Авторизация required")
    mock_page.close = AsyncMock()
    
    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    
    routers.observer.CONTEXT_INSTANCE = mock_context
    
    with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=None)):
        response = client.get("/api/observer/123987")
        assert response.status_code == 200
        assert response.json()["status"] == "error"
        assert "Auth expired" in response.json()["message"]

def test_observer_scrape_success():
    import routers.observer
    
    mock_element = AsyncMock()
    mock_element.evaluate = AsyncMock(return_value='<div src="/" href="/"></div>')
    
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
    
    with patch("aiosqlite.connect", return_value=MockConnection(fetchone_data=None)): # DB miss
        response = client.get("/api/observer/123987")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert "source" in response.json()
        
        html = response.json()["html"]
        assert "pwobs.com/" in html # Check standard replacement
        assert "style.css" in html # Check CSS bundle
