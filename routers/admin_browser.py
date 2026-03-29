import asyncio
import json
import logging
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import Response
from playwright.async_api import async_playwright

# Configuration
# Configuration
AUTH_FILE = "pwobs_auth.json"
# Ensure sessions dir exists - REMOVED


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
        self.last_error = None
        self.lock = asyncio.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = RemoteBrowserSession()
        return cls._instance

    async def _launch_browser_task(self, url):
        async with self.lock:
            try:
                self.last_error = None
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
                        "--disable-software-rasterizer",
                    ],
                )

                # Load auth state if exists
                state = None
                if os.path.exists(AUTH_FILE):
                    if os.path.isdir(AUTH_FILE):
                        logger.error(f"{AUTH_FILE} is a directory! Ignoring it. Please remove it manually on server.")
                        # We cannot use it if it is a directory.
                        state = None
                    else:
                        try:
                            # Pre-validate JSON to avoid crashing Playwright
                            with open(AUTH_FILE, "r", encoding="utf-8") as f:
                                content = f.read().strip()
                                if not content:
                                    logger.warning(f"{AUTH_FILE} is empty. Starting fresh session.")
                                    state = None
                                else:
                                    json.loads(content)  # Verify valid JSON
                                    state = AUTH_FILE
                                    logger.info(f"Loading state from {AUTH_FILE}")
                        except json.JSONDecodeError as je:
                            logger.error(f"Corrupted auth file (JSON error): {je}. Starting fresh.")
                            state = None
                        except Exception as e:
                            logger.error(f"Failed to validate state file: {e}")
                            state = None

                self.context = await self.browser.new_context(storage_state=state)

                # Setup popup handling
                self.main_page = await self.context.new_page()
                self.page = self.main_page  # Active page
                await self.page.set_viewport_size({"width": 1280, "height": 720})

                # Listen for new pages (popups like Telegram Login)
                self.context.on("page", self._on_popup)

                logger.info(f"Navigating to {url}...")
                await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                self.is_active = True
                print("DEBUG: _launch_browser_task FINISHED")
                logger.info("Browser started successfully.")

            except Exception as e:
                self.last_error = str(e)
                logger.error(f"Failed to start browser session: {e}")
                try:
                    await self.stop_session()
                except Exception:
                    pass

    def _on_popup(self, page):
        """Handle new popup windows (e.g. OAuth login)"""
        logger.info("New popup detected! Switching focus.")
        self.page = page

        # Ensure viewport matches for consistency
        try:
            # We can't await here directly in sync callback easily, but page.set_viewport_size is async.
            # However, Playwright event handlers can be async.
            asyncio.create_task(self._setup_popup(page))
        except Exception as e:
            logger.error(f"Error handling popup: {e}")

    async def _setup_popup(self, page):
        try:
            await page.set_viewport_size({"width": 1280, "height": 720})

            # Listen for close
            page.on("close", self._on_popup_close)
        except Exception as e:
            logger.error(f"Setup popup failed: {e}")

    def _on_popup_close(self, page):
        logger.info("Popup closed. Reverting to main page.")
        self.page = self.main_page

    async def start_session(self, background_tasks: BackgroundTasks, url="https://pwobs.com/login"):
        if self.is_active:
            return {"status": "ok", "message": "Session already active"}

        # Reset error on new start
        self.last_error = None
        # Schedule the heavy lifting
        background_tasks.add_task(self._launch_browser_task, url)
        return {"status": "ok", "message": "Browser initialization started..."}

    async def get_screenshot(self):
        if not self.is_active:
            raise HTTPException(status_code=404, detail="Session not active")

        # Recovery: If page is missing but we are active, try to recover main page
        if not self.page:
            if hasattr(self, "main_page") and self.main_page:
                logger.warning("Active session had no page! Recovering to main_page.")
                self.page = self.main_page
            else:
                raise HTTPException(status_code=503, detail="Session active but page is lost.")

        # Recovery: Check if page is closed
        if self.page.is_closed():
            if hasattr(self, "main_page") and self.main_page and not self.main_page.is_closed():
                logger.warning("Current page is closed. Reverting to main_page.")
                self.page = self.main_page
            else:
                # Both closed?
                await self.stop_session()
                raise HTTPException(status_code=503, detail="All pages closed.")

        try:
            # Capture as JPEG for speed
            data = await self.page.screenshot(type="jpeg", quality=60)
            return Response(content=data, media_type="image/jpeg")
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            # If screenshot fails, the browser is likely dead.
            await self.stop_session()
            raise HTTPException(status_code=503, detail=f"Browser Error: {str(e)}")

    async def stop_session(self, save: bool = True):
        async with self.lock:
            # Optionally save state before closing - NOW DEFAULT TRUE
            if self.is_active and self.context:
                try:
                    logger.info(f"Attempting to save auth state to {AUTH_FILE}...")
                    await self.context.storage_state(path=AUTH_FILE)
                    if os.path.exists(AUTH_FILE):
                        size = os.path.getsize(AUTH_FILE)
                        logger.info(f"✅ Auth state saved successfully to {AUTH_FILE} ({size} bytes)")
                    else:
                        logger.error(f"❌ storage_state CALLED but {AUTH_FILE} was NOT CREATED!")
                except Exception as e:
                    logger.error(f"❌ Failed to save state during stop: {e}")

            # Always try to cleanup, even if is_active=False (cleanup failed start)
            try:
                if self.browser:
                    await self.browser.close()
                if self.playwright:
                    await self.playwright.stop()
            except Exception as e:
                logger.error(f"Failed to stop browser session: {e}")
            finally:
                self.is_active = False
                self.browser = None
                self.context = None
                self.page = None
                self.playwright = None

            return {"status": "ok", "message": "Browser session stopped." + (" (Saved)" if save else "")}

    async def save_session_state(self):
        async with self.lock:
            if not self.is_active or not self.context:
                return {"status": "error", "message": "No active session to save"}

            try:
                await self.context.storage_state(path=AUTH_FILE)
                abs_path = os.path.abspath(AUTH_FILE)
                logger.info(f"Auth state explicitly saved to {AUTH_FILE} (Abs: {abs_path})")
                return {"status": "ok", "message": f"Saved to {AUTH_FILE}"}
            except Exception as e:
                logger.error(f"Failed to save state: {e}")
                return {"status": "error", "message": f"Save failed: {e}"}

    async def get_status(self):
        url = "Unknown"
        if self.page and not self.page.is_closed():
            try:
                url = self.page.url
            except Exception:
                pass

        return {"active": self.is_active, "last_error": self.last_error, "url": url}

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
                if text is not None:
                    # If selector provided, type there. If not, just type (key press)
                    if selector:
                        await self.page.fill(selector, text)
                    else:
                        await self.page.keyboard.type(text)
                    return {"status": "ok", "message": f"Typed '{text}'"}
                else:
                    raise HTTPException(status_code=400, detail="Missing text for type action")
            elif action_type == "press":
                key = action.get("key")
                if key:
                    await self.page.keyboard.press(key)
                    return {"status": "ok", "message": f"Pressed {key}"}
                else:
                    raise HTTPException(status_code=400, detail="Missing key for press action")
            elif action_type == "goto":
                url = action.get("url")
                if url:
                    await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    return {"status": "ok", "message": f"Navigated to {url}"}
                else:
                    raise HTTPException(status_code=400, detail="Missing url for goto action")
            elif action_type == "scroll":
                x, y = action.get("x", 0), action.get("y", 0)
                await self.page.evaluate(f"window.scrollBy({x}, {y})")
                return {"status": "ok", "message": f"Scrolled by ({x}, {y})"}
            else:
                raise HTTPException(status_code=400, detail=f"Unknown action type: {action_type}")
        except HTTPException:
            raise
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


@router.get("/status")
async def get_status():
    return await session_manager.get_status()


@router.post("/interact")
async def interact(action: dict):
    # Expects JSON body: {"type": "click", "x": 100, "y": 200} etc
    return await session_manager.handle_input(action)


@router.post("/stop")
async def stop_browser(save: bool = True):
    return await session_manager.stop_session(save=save)


@router.post("/save")
async def save_browser_state():
    return await session_manager.save_session_state()


@router.get("/debug/files")
async def list_session_files():
    """List files in the sessions directory to verify persistence."""
    try:
        if not os.path.exists("sessions"):
            return {"status": "error", "message": "'sessions' directory does not exist!"}

        files = []
        for f in os.listdir("sessions"):
            path = os.path.join("sessions", f)
            stat = os.stat(path)
            files.append({"name": f, "size": stat.st_size, "modified": stat.st_mtime})

        # Check permissions
        can_write = os.access("sessions", os.W_OK)

        return {"status": "ok", "directory": os.path.abspath("sessions"), "writable": can_write, "files": files}
    except Exception as e:
        return {"status": "error", "message": str(e)}
