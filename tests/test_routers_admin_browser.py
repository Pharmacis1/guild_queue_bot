import asyncio
import json
import os
import pytest
from fastapi.testclient import TestClient

from main import app
from routers import admin_browser


# --- Playwright Mocks ---

class MockKeyboard:
    async def type(self, text):
        pass
        
    async def press(self, key):
        pass

class MockMouse:
    async def click(self, x, y):
        pass

class MockPage:
    def __init__(self, url="https://mock.example.com"):
        self.url = url
        self.closed = False
        self.viewport = None
        self.keyboard = MockKeyboard()
        self.mouse = MockMouse()
        self.events = {}

    def is_closed(self):
        return self.closed

    async def set_viewport_size(self, size):
        self.viewport = size

    async def goto(self, url):
        self.url = url

    async def fill(self, selector, text):
        pass

    async def evaluate(self, script):
        pass

    async def screenshot(self, type="jpeg", quality=60):
        # Return fake jpeg bytes
        return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x05\x03\x04\x04\x04\x03\x05\x04\x04\x04\x05\x05\x05\x06\x07\x0c\x08\x07\x07\x07\x0f\x0b\x0b\t\x0c\x11\x0f\x12\x12\x11\x0f\x11\x11\x13\x16\x1c\x17\x13\x14\x1a\x15\x11\x11\x18!\x18\x1a\x1d\x1d\x1f\x1f\x1f\x13\x17\"#\x1f\"\x1f &"

    def on(self, event, handler):
        self.events[event] = handler

class MockContext:
    def __init__(self):
        self.events = {}

    async def new_page(self):
        return MockPage()
        
    async def storage_state(self, path=None):
        if path:
            with open(path, "w") as f:
                f.write(json.dumps({"mock": "state"}))

    def on(self, event, handler):
        self.events[event] = handler

class MockBrowser:
    def __init__(self):
        self.closed = False
        
    async def new_context(self, storage_state=None):
        return MockContext()

    async def close(self):
        self.closed = True

class MockPlaywrightChromium:
    async def launch(self, headless=True, args=None):
        return MockBrowser()

class MockPlaywright:
    def __init__(self):
        self.chromium = MockPlaywrightChromium()
        self.stopped = False

    async def start(self):
        return self

    async def stop(self):
        self.stopped = True

class MockAsyncPlaywright:
    async def start(self):
        return MockPlaywright()


# --- Fixtures ---

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def cleanup_browser_session():
    # Before each test, reset the singleton
    admin_browser.session_manager.is_active = False
    admin_browser.session_manager.browser = None
    admin_browser.session_manager.context = None
    admin_browser.session_manager.page = None
    admin_browser.session_manager.main_page = None
    admin_browser.session_manager.playwright = None
    
    yield
    
    # Cleanup dummy files
    if os.path.exists(admin_browser.AUTH_FILE) and not os.path.isdir(admin_browser.AUTH_FILE):
        os.remove(admin_browser.AUTH_FILE)


@pytest.fixture
def mock_playwright(monkeypatch):
    monkeypatch.setattr(admin_browser, "async_playwright", MockAsyncPlaywright)


# --- Tests ---

@pytest.mark.asyncio
async def test_session_lifecycle(client, mock_playwright):
    # GET status when not active
    resp = client.get("/api/browser/status")
    assert resp.status_code == 200
    assert resp.json()["active"] is False

    # POST start
    resp = client.post("/api/browser/start")
    assert resp.status_code == 200
    assert "started" in resp.json()["message"]

    # In FastAPI TestClient, BackgroundTasks are executed synchronously *after* returning the response.
    # The TestClient inherently waits for it. So the session_manager should be active now.
    
    # POST start again (already active)
    resp2 = client.post("/api/browser/start")
    assert resp2.json()["message"] == "Session already active"

    # GET status
    resp3 = client.get("/api/browser/status")
    assert resp3.json()["active"] is True

    # POST stop
    resp4 = client.post("/api/browser/stop")
    assert resp4.json()["status"] == "ok"

    # GET status after stop
    resp5 = client.get("/api/browser/status")
    assert resp5.json()["active"] is False

@pytest.mark.asyncio
async def test_screenshot(client, mock_playwright):
    # Failed screenshot (not active)
    resp = client.get("/api/browser/screenshot")
    assert resp.status_code == 404

    # Start browser
    client.post("/api/browser/start")

    # Success screenshot
    resp2 = client.get("/api/browser/screenshot")
    assert resp2.status_code == 200
    assert resp2.headers["content-type"] == "image/jpeg"
    assert len(resp2.content) > 0

@pytest.mark.asyncio
async def test_interact(client, mock_playwright):
    # Not active
    resp = client.post("/api/browser/interact", json={"type": "click"})
    assert resp.status_code == 404

    client.post("/api/browser/start")

    # Click
    resp_click = client.post("/api/browser/interact", json={"type": "click", "x": 100, "y": 100})
    assert resp_click.status_code == 200

    # Click missing coords
    resp_err = client.post("/api/browser/interact", json={"type": "click"})
    assert resp_err.status_code == 400
    assert "Missing x, y" in resp_err.json()["detail"]

    # Type with selector
    resp_type1 = client.post("/api/browser/interact", json={"type": "type", "selector": "#id", "text": "hello"})
    assert resp_type1.status_code == 200

    # Type without selector (keyboard focus)
    resp_type2 = client.post("/api/browser/interact", json={"type": "type", "text": "hello"})
    assert resp_type2.status_code == 200

    # Press
    resp_press = client.post("/api/browser/interact", json={"type": "press", "key": "Enter"})
    assert resp_press.status_code == 200

    # Goto
    resp_goto = client.post("/api/browser/interact", json={"type": "goto", "url": "http://foo.bar"})
    assert resp_goto.status_code == 200

    # Scroll
    resp_scroll = client.post("/api/browser/interact", json={"type": "scroll", "y": 500})
    assert resp_scroll.status_code == 200

    # Invalid action
    resp_inv = client.post("/api/browser/interact", json={"type": "magic"})
    assert resp_inv.status_code == 400

@pytest.mark.asyncio
async def test_save_state(client, mock_playwright):
    # Not active
    resp = client.post("/api/browser/save")
    assert resp.json()["status"] == "error"

    client.post("/api/browser/start")

    resp2 = client.post("/api/browser/save")
    assert resp2.json()["status"] == "ok"
    assert os.path.exists(admin_browser.AUTH_FILE)

@pytest.mark.asyncio
async def test_start_with_existing_auth(client, mock_playwright):
    # Create valid auth json
    with open(admin_browser.AUTH_FILE, "w") as f:
        json.dumps({"test": 1})
        f.write('{"test": 1}')
    
    # Start
    resp = client.post("/api/browser/start")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_start_with_corrupt_auth(client, mock_playwright):
    # Create invalid auth
    with open(admin_browser.AUTH_FILE, "w") as f:
        f.write('{not json')
    
    # Start should log error and continue fresh
    resp = client.post("/api/browser/start")
    assert resp.status_code == 200
    assert admin_browser.session_manager.is_active

@pytest.mark.asyncio
async def test_debug_files_dir_missing(client, monkeypatch):
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    resp = client.get("/api/browser/debug/files")
    assert resp.json()["status"] == "error"

@pytest.mark.asyncio
async def test_debug_files_dir_exists(client, monkeypatch):
    import stat
    monkeypatch.setattr(os.path, "exists", lambda p: True)
    monkeypatch.setattr(os.path, "isdir", lambda p: True)
    monkeypatch.setattr(os, "listdir", lambda p: ["file1.txt"])
    
    class FakeStat:
        st_size = 100
        st_mtime = 1234.0
    monkeypatch.setattr(os, "stat", lambda p: FakeStat())
    monkeypatch.setattr(os, "access", lambda p, m: True)

    resp = client.get("/api/browser/debug/files")
    assert resp.json()["status"] == "ok"
    assert len(resp.json()["files"]) == 1

@pytest.mark.asyncio
async def test_start_with_corrupt_auth_dir(client, mock_playwright):
    # Simulate AUTH_FILE is a directory
    import os
    if not os.path.exists(admin_browser.AUTH_FILE):
        os.mkdir(admin_browser.AUTH_FILE)
    
    resp = client.post("/api/browser/start")
    assert resp.status_code == 200

    import shutil
    shutil.rmtree(admin_browser.AUTH_FILE)

@pytest.mark.asyncio
async def test_screenshot_missing_page_recovery(client, mock_playwright):
    client.post("/api/browser/start")
    
    # Intentionally corrupt the active page state
    admin_browser.session_manager.page = None
    resp = client.get("/api/browser/screenshot")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_screenshot_closed_page_recovery(client, mock_playwright):
    client.post("/api/browser/start")
    
    # Simulate a popup overtaking the active page
    admin_browser.session_manager.page = MockPage()
    admin_browser.session_manager.page.closed = True
    
    resp = client.get("/api/browser/screenshot")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_screenshot_all_closed(client, mock_playwright):
    client.post("/api/browser/start")
    
    admin_browser.session_manager.page.closed = True
    admin_browser.session_manager.main_page.closed = True
    
    resp = client.get("/api/browser/screenshot")
    assert resp.status_code == 503

@pytest.mark.asyncio
async def test_browser_launch_failure(client, monkeypatch):
    # Force a failure during browser launch
    class MockFailingPlaywright:
        async def start(self):
            raise Exception("Simulated Browser Crash")
            
    monkeypatch.setattr(admin_browser, "async_playwright", MockFailingPlaywright)
    client.post("/api/browser/start")
    
    # Wait for background task sync side-effects
    resp = client.get("/api/browser/status")
    assert "Simulated Browser Crash" in resp.json()["last_error"]
