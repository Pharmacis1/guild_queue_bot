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

    async def start_session(self, url="https://pwobs.com/login"):
        async with self.lock:
            if self.is_active:
                if self.page:
                    await self.page.goto(url)
                return {"status": "ok", "message": "Session already active, navigated to URL"}

            logger.info("Starting Remote Browser Session...")
            self.playwright = await async_playwright().start()
            
            # Use headless=True normally, but for visual debugging we might want False locally.
            # However, since we are streaming screenshots, headless=True is fine and preferred for servers.
            self.browser = await self.playwright.chromium.launch(headless=True)
            
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
            
            # Set viewport to something reasonable for desktop view
            await self.page.set_viewport_size({"width": 1280, "height": 720})

            try:
                await self.page.goto(url)
                self.is_active = True
                return {"status": "ok", "message": "Browser started"}
            except Exception as e:
                await self.stop_session()
                raise HTTPException(status_code=500, detail=f"Failed to navigate: {str(e)}")

    async def get_screenshot(self):
        if not self.is_active or not self.page:
            # Return a placeholder image or error
            raise HTTPException(status_code=400, detail="Session not active")
        
        try:
            # Capture as JPEG for speed
            data = await self.page.screenshot(type="jpeg", quality=60)
            return Response(content=data, media_type="image/jpeg")
        except Exception as e:
             logger.error(f"Screenshot failed: {e}")
             raise HTTPException(status_code=500, detail="Screenshot failed")

    async def handle_input(self, action: dict):
        if not self.is_active or not self.page:
            raise HTTPException(status_code=400, detail="Session not active")

        try:
            action_type = action.get("type")
            
            if action_type == "click":
                x = action.get("x")
                y = action.get("y")
                await self.page.mouse.click(x, y)
                
            elif action_type == "type":
                text = action.get("text")
                if text:
                    await self.page.keyboard.type(text)
            
            elif action_type == "press":
                key = action.get("key") # Enter, Backspace, etc
                if key:
                    await self.page.keyboard.press(key)
            
            return {"status": "ok"}
            
        except Exception as e:
            logger.error(f"Input handling failed: {e}")
            return {"status": "error", "message": str(e)}

    async def stop_session(self):
        async with self.lock:
            if not self.is_active:
                return {"status": "ok", "message": "Already stopped"}
            
            logger.info("Stopping Remote Browser Session...")
            try:
                # Save state!
                if self.context:
                    await self.context.storage_state(path=AUTH_FILE)
                    logger.info("Auth state saved.")

                if self.page: await self.page.close()
                if self.context: await self.context.close()
                if self.browser: await self.browser.close()
                if self.playwright: await self.playwright.stop()
            except Exception as e:
                logger.error(f"Error stopping session: {e}")
            finally:
                self.page = None
                self.context = None
                self.browser = None
                self.playwright = None
                self.is_active = False
                
            return {"status": "ok", "message": "Session stopped and saved"}

# --- Endpoints ---

session_manager = RemoteBrowserSession.get_instance()

@router.post("/start")
async def start_browser():
    return await session_manager.start_session()

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
