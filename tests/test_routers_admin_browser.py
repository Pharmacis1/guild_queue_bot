import json
import os
import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock

from main import app
from routers import admin_browser

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def setup_mocks(monkeypatch):
    mgr = admin_browser.session_manager
    
    # Mock methods directly on the existing instance
    mgr.start_session = AsyncMock(return_value={"status": "ok", "message": "Browser initialization started..."})
    mgr.stop_session = AsyncMock(return_value={"status": "ok"})
    
    async def mock_status():
        return {"active": mgr.is_active, "last_error": mgr.last_error, "url": "http://test"}
    mgr.get_status = AsyncMock(side_effect=mock_status)
    
    async def mock_screenshot():
        if not mgr.is_active:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Session not active")
        from fastapi.responses import Response
        return Response(content=b"fake_image", media_type="image/jpeg")
    mgr.get_screenshot = AsyncMock(side_effect=mock_screenshot)
    
    async def mock_interact(data):
        if not mgr.is_active:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Session not active")
        return {"status": "ok"}
    mgr.handle_input = AsyncMock(side_effect=mock_interact)
    
    mgr.save_session_state = AsyncMock(return_value={"status": "ok"})
    
    # Ensure attributes are reset
    mgr.is_active = False
    mgr.last_error = None

    yield mgr
    
    # Reset for next test
    mgr.is_active = False
    mgr.last_error = None

def test_session_lifecycle(client):
    mgr = admin_browser.session_manager
    # Not active
    resp = client.get("/api/browser/status")
    assert resp.status_code == 200
    assert resp.json()["active"] is False

    # Start
    resp = client.post("/api/browser/start")
    assert resp.status_code == 200
    
    mgr.is_active = True
    resp = client.get("/api/browser/status")
    assert resp.json()["active"] is True

    # Stop
    resp = client.post("/api/browser/stop")
    assert resp.json()["status"] == "ok"
    mgr.is_active = False

def test_screenshot(client):
    mgr = admin_browser.session_manager
    # Failed
    resp = client.get("/api/browser/screenshot")
    assert resp.status_code == 404

    # Success
    mgr.is_active = True
    resp = client.get("/api/browser/screenshot")
    assert resp.status_code == 200
    assert resp.content == b"fake_image"

def test_interact(client):
    mgr = admin_browser.session_manager
    # Failed
    resp = client.post("/api/browser/interact", json={"type": "click"})
    assert resp.status_code == 404

    # Success
    mgr.is_active = True
    resp = client.post("/api/browser/interact", json={"type": "click", "x": 100, "y": 100})
    assert resp.status_code == 200

def test_save_state(client):
    mgr = admin_browser.session_manager
    mgr.is_active = True
    resp = client.post("/api/browser/save")
    assert resp.json()["status"] == "ok"

def test_debug_files(client, monkeypatch):
    monkeypatch.setattr(os, "listdir", lambda p: ["mock.txt"])
    monkeypatch.setattr(os.path, "exists", lambda p: True)
    monkeypatch.setattr(os, "stat", lambda p: MagicMock(st_size=10, st_mtime=1.0))
    resp = client.get("/api/browser/debug/files")
    assert resp.status_code == 200
    assert "mock.txt" in [f["name"] for f in resp.json()["files"]]
