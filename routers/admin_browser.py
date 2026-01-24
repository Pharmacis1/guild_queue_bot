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
                    args=[
                        "--no-sandbox", 
                        "--disable-setuid-sandbox", 
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-software-rasterizer"
                    ]
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

    async def get_screenshot(self):
        if not self.is_active or not self.page:
            # Return a simple placeholder JSON or text if not active, 
            # but usually frontend expects image. Let's return 404 to stop polling.
            raise HTTPException(status_code=404, detail="Session not active")
        
        try:
            # Capture as JPEG for speed
            data = await self.page.screenshot(type="jpeg", quality=60)
            return Response(content=data, media_type="image/jpeg")
        except Exception as e:
             logger.error(f"Screenshot failed: {e}")
             # If screenshot fails, the browser is likely dead.
             await self.stop_session()
             raise HTTPException(status_code=503, detail=f"Browser Error: {str(e)}")

    async def stop_session(self):
        async with self.lock:
            if not self.is_active:
                return {"status": "ok", "message": "Session not active"}
            
            try:
                if self.browser:
                    await self.browser.close()
                if self.playwright:
                    await self.playwright.stop()
                self.is_active = False
                self.browser = None
                self.context = None
                self.page = None
                self.playwright = None
                logger.info("Browser session stopped.")
                return {"status": "ok", "message": "Browser session stopped."}
            except Exception as e:
                logger.error(f"Failed to stop browser session: {e}")
                return {"status": "error", "message": f"Failed to stop browser session: {e}"}

    async def handle_input(self, action: dict):
        if not self.is_active or not self.page:
            raise HTTPException(status_code=404, detail="Session not active")
        
        action_type = action.get("type")
        try:
            if action_type == "click":
                x, y = action.get("x"), action.get("y")
                if x is not None and y is not None:
                    await self.page.mouse.click(x, y)
                    return {"status": "ok", "message": f"Clicked at ({x}, {y})"}
                else:
                    raise HTTPException(status_code=400, detail="Missing x, y for click action")
            elif action_type == "type":
                selector = action.get("selector")
                text = action.get("text")
                if selector and text is not None:
                    await self.page.fill(selector, text)
                    return {"status": "ok", "message": f"Typed '{text}' into '{selector}'"}
                else:
                    raise HTTPException(status_code=400, detail="Missing selector or text for type action")
            elif action_type == "goto":
                url = action.get("url")
                if url:
                    await self.page.goto(url)
                    return {"status": "ok", "message": f"Navigated to {url}"}
                else:
                    raise HTTPException(status_code=400, detail="Missing url for goto action")
            elif action_type == "scroll":
                x, y = action.get("x", 0), action.get("y", 0)
                await self.page.evaluate(f"window.scrollBy({x}, {y})")
                return {"status": "ok", "message": f"Scrolled by ({x}, {y})"}
            else:
                raise HTTPException(status_code=400, detail=f"Unknown action type: {action_type}")
        except Exception as e:
            logger.error(f"Interaction failed: {e}")
            raise HTTPException(status_code=500, detail=f"Interaction failed: {e}")


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
