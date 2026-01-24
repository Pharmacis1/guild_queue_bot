from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import Response, JSONResponse
from playwright.async_api import async_playwright, Page, BrowserContext, Browser
import asyncio
import logging
import os
import json

# Configuration
AUTH_FILE = "pwobs_auth.json"
router = APIRouter(prefix="/api/browser", tags=["admin_browser"])
logger = logging.getLogger("admin_browser")

class RemoteBrowserSession:
    _instance = None

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.is_active = False
        self.lock = asyncio.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = RemoteBrowserSession()
        return cls._instance

    async def _launch_browser_task(self, url):
        async with self.lock:
            try:
                logger.info("Starting Remote Browser Session (Background)...")
                self.playwright = await async_playwright().start()
                
                # Docker requires no-sandbox usually
                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                
                # Load auth state if exists
                state = None
                if os.path.exists(AUTH_FILE):
                    try:
                        state = AUTH_FILE
                        logger.info(f"Loading state from {AUTH_FILE}")
                    except Exception as e:
                        logger.error(f"Failed to load state: {e}")

                self.context = await self.browser.new_context(storage_state=state)
                self.page = await self.context.new_page()
                await self.page.set_viewport_size({"width": 1280, "height": 720})

                logger.info(f"Navigating to {url}...")
                await self.page.goto(url)
                self.is_active = True
                logger.info("Browser started successfully.")
                
            except Exception as e:
                logger.error(f"Failed to start browser session: {e}")
                try: await self.stop_session() 
                except: pass

    async def start_session(self, background_tasks: BackgroundTasks, url="https://pwobs.com/login"):
        if self.is_active:
             return {"status": "ok", "message": "Session already active"}
        
        # Schedule the heavy lifting
        background_tasks.add_task(self._launch_browser_task, url)
        return {"status": "ok", "message": "Browser initialization started..."}

# --- Endpoints ---

session_manager = RemoteBrowserSession.get_instance()

@router.post("/start")
async def start_browser(background_tasks: BackgroundTasks):
    return await session_manager.start_session(background_tasks)

@router.get("/screenshot")
async def get_screenshot():
    return await session_manager.get_screenshot()

@router.post("/interact")
async def interact(action: dict):
    # Expects JSON body: {"type": "click", "x": 100, "y": 200} etc
    return await session_manager.handle_input(action)

@router.post("/stop")
async def stop_browser():
    return await session_manager.stop_session()
