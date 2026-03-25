import asyncio
import logging
import os
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Depends
from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright
from database import AsyncSessionLocal, ObserverCache, get_msk_now, get_session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

router = APIRouter()

# Global State
PLAYWRIGHT_INSTANCE: Playwright = None
BROWSER_INSTANCE: Browser = None
CONTEXT_INSTANCE: BrowserContext = None
LOCK = asyncio.Lock()

CACHE_TTL_HOURS = 1  # How long to keep HTML in cache


async def init_browser():
    """Initializes the global Playwright browser instance."""
    global PLAYWRIGHT_INSTANCE, BROWSER_INSTANCE, CONTEXT_INSTANCE

    if BROWSER_INSTANCE:
        return

    logging.info("🚀 Launching Observer Browser...")
    try:
        PLAYWRIGHT_INSTANCE = await async_playwright().start()
        # Headless for production, but you can toggle for debug
        BROWSER_INSTANCE = await PLAYWRIGHT_INSTANCE.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],  # Docker friendly
        )
        context_args = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "viewport": {"width": 1280, "height": 720},
        }

        if os.path.exists("pwobs_auth.json"):
            logging.info("🔑 Loading PWOBS auth state...")
            context_args["storage_state"] = "pwobs_auth.json"

        CONTEXT_INSTANCE = await BROWSER_INSTANCE.new_context(**context_args)
        logging.info("✅ Observer Browser Ready.")
    except Exception as e:
        logging.error(f"❌ Failed to launch browser: {e}")


async def close_browser():
    """Closes the browser on shutdown."""
    global PLAYWRIGHT_INSTANCE, BROWSER_INSTANCE, CONTEXT_INSTANCE
    if CONTEXT_INSTANCE:
        await CONTEXT_INSTANCE.close()
    if BROWSER_INSTANCE:
        await BROWSER_INSTANCE.close()
    if PLAYWRIGHT_INSTANCE:
        await PLAYWRIGHT_INSTANCE.stop()
    CONTEXT_INSTANCE = None
    BROWSER_INSTANCE = None
    PLAYWRIGHT_INSTANCE = None
    logging.info("💤 Observer Browser Closed.")


async def reload_context():
    """Re-creates the browser context to load the latest auth state."""
    global BROWSER_INSTANCE, CONTEXT_INSTANCE
    async with LOCK:
        if not BROWSER_INSTANCE:
            await init_browser()
            return

        logging.info("🔄 Reloading Observer Context (new auth state)...")
        if CONTEXT_INSTANCE:
            await CONTEXT_INSTANCE.close()
        
        context_args = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "viewport": {"width": 1280, "height": 720},
        }

        if os.path.exists("pwobs_auth.json"):
            logging.info("🔑 Loading NEW PWOBS auth state...")
            context_args["storage_state"] = "pwobs_auth.json"

        CONTEXT_INSTANCE = await BROWSER_INSTANCE.new_context(**context_args)
        logging.info("✅ Observer Context Reloaded.")


@router.get("/api/observer_stats")
async def get_stats():
    """Debug endpoint to check browser status"""
    logging.info("Checking observer stats...")
    return {"browser_active": BROWSER_INSTANCE is not None, "context_active": CONTEXT_INSTANCE is not None}


@router.get("/api/observer/{role_id}")
async def get_player_equipment(role_id: int, server: str = "capella", session: AsyncSession = Depends(get_session)):
    """
    Returns the HTML snippet for the player's equipment.
    Uses caching to avoid spamming PWOBS.
    """
    if not role_id:
        raise HTTPException(status_code=400, detail="Missing role_id")

    # 1. Check Cache
    result = await session.execute(select(ObserverCache).filter_by(role_id=role_id))
    cache_entry = result.scalar_one_or_none()
    
    if cache_entry:
        if get_msk_now() - cache_entry.updated_at < timedelta(hours=CACHE_TTL_HOURS):
            logging.info(f"Cache HIT for {role_id}")
            return {"status": "ok", "html": cache_entry.html_content, "source": "cache"}

    # 2. Scrape
    if not CONTEXT_INSTANCE:
        await init_browser()
        if not CONTEXT_INSTANCE:
            raise HTTPException(status_code=500, detail="Browser not initialized")

    logging.info(f"Scraping PWOBS for {role_id}...")

    async def do_scrape(attempt=1):
        page = None
        try:
            page = await CONTEXT_INSTANCE.new_page()
            url = f"https://pwobs.com/{server}/players/{role_id}"
            # domcontentloaded is faster and less prone to timeout from tracking scripts
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")

            # Check for login redirection
            title = await page.title()
            if any(word in title for word in ["Авторизация", "Вход", "Login"]):
                if attempt == 1 and os.path.exists("pwobs_auth.json"):
                    logging.info("Login detected! Attempting context reload...")
                    await page.close()
                    await reload_context()
                    return await do_scrape(attempt=2)
                return {"status": "error", "message": "PWOBS requires login (Session expired or missing)"}

            # Wait for selector
            selector = ".player-equipment"
            try:
                # First wait for the container
                await page.wait_for_selector(selector, timeout=20000)
                # Then wait for at least one item to ensure Vue has rendered the data
                # If the player is naked, this might timeout, so we use a shorter timeout here
                try:
                    await page.wait_for_selector(".player-equipment__item", timeout=10000)
                    logging.info("✅ Equipment items detected.")
                except Exception:
                    logging.warning("⚠️ No equipment items detected after 10s, returning what we have.")
                
                # Small extra buffer for final rendering
                await page.wait_for_timeout(1000)
            except Exception:
                if "404" in await page.title():
                    return {"status": "error", "message": "Player not found on PWOBS"}
                return {"status": "error", "message": "Equipment block not found (timeout 20s)"}

            # Extract HTML (Simplified for brevity in replacement)
            css_links = await page.evaluate("() => Array.from(document.querySelectorAll('link[rel=\"stylesheet\"]')).map(link => link.href)")
            element = await page.query_selector(selector)
            if not element: return {"status": "error", "message": "Element vanished"}
            html_content = await element.evaluate("el => el.outerHTML")

            # Fix links
            html_content = html_content.replace('src="/', 'src="https://pwobs.com/')
            html_content = html_content.replace('href="/', 'href="https://pwobs.com/')

            # Wrap and Style
            full_html = "".join([f'<link rel="stylesheet" href="{l}">' for l in css_links])
            full_html += """
            <style>
                body { 
                    background: transparent !important; 
                    overflow: visible !important; 
                    height: auto !important;
                    min-height: 600px;
                    padding-top: 150px; 
                    padding-bottom: 150px; 
                    padding-right: 50px;
                    padding-left: 50px;
                } 
                .player-equipment { 
                    margin: 0 auto; 
                    transform: scale(0.9); 
                    transform-origin: center center;
                }
                
                /* FORCE TOOLTIP VISIBILITY ON HOVER */
                .player-equipment__item:hover .player-equipment__item-tooltip {
                    opacity: 1 !important;
                    visibility: visible !important;
                    display: block !important;
                    z-index: 99999;
                    position: absolute;
                    background: rgba(0,0,0,0.95);
                    border: 1px solid #555;
                    padding: 10px;
                    border-radius: 5px;
                    color: #fff;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.5);
                    min-width: 250px;
                }
            </style>
            """
            full_html += html_content

            # Cache
            # We need to re-fetch session entry or use the one we have
            return {"status": "ok", "html": full_html, "source": "live"}
        except Exception as e:
            logging.error(f"Scrape error (attempt {attempt}): {e}")
            return {"status": "error", "message": str(e)}
        finally:
            if page: await page.close()

    scrape_res = await do_scrape()
    if scrape_res.get("status") == "ok":
        # Save to DB (using external session/entry logic)
        result = await session.execute(select(ObserverCache).filter_by(role_id=role_id))
        entry = result.scalar_one_or_none()
        if not entry:
            entry = ObserverCache(role_id=role_id)
            session.add(entry)
        entry.html_content = scrape_res["html"]
        entry.updated_at = get_msk_now()
        await session.commit()
    
    return scrape_res
