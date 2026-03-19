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
    global PLAYWRIGHT_INSTANCE, BROWSER_INSTANCE
    if BROWSER_INSTANCE:
        await BROWSER_INSTANCE.close()
    if PLAYWRIGHT_INSTANCE:
        await PLAYWRIGHT_INSTANCE.stop()
    logging.info("💤 Observer Browser Closed.")


@router.get("/api/observer_stats")
async def get_stats():
    """Debug endpoint to check browser status"""
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

    # 2. Scrape (Protected by Lock to avoid crashing browser with parallel tabs if resource constrained)
    # PWOBS prevents too many requests? We can parallelize carefully.
    # For now, let's keep it simple: Create new page, scrape, close page.

    if not CONTEXT_INSTANCE:
        await init_browser()
        if not CONTEXT_INSTANCE:
            raise HTTPException(status_code=500, detail="Browser not initialized")

    logging.info(f"Scraping PWOBS for {role_id}...")

    page = None
    try:
        page = await CONTEXT_INSTANCE.new_page()
        url = f"https://pwobs.com/{server}/players/{role_id}"

        # Navigate
        # Wait for networkidle to ensure Vue.js fetches all item stats
        await page.goto(url, timeout=30000, wait_until="networkidle")

        # Wait for selector
        selector = ".player-equipment"
        try:
            # Check for login redirection early
            if "Авторизация" in await page.title():
                return {"status": "error", "message": "PWOBS requires login (Auth expired?)"}

            await page.wait_for_selector(selector, timeout=20000)
            # Extra wait for Vue to populate the empty divs with stats
            await page.wait_for_timeout(2000)
        except Exception:
            # Check if 404
            title = await page.title()
            if "404" in title:
                return {"status": "error", "message": "Player not found on PWOBS"}
            if "Авторизация" in title:
                return {"status": "error", "message": "PWOBS requires login"}

            return {"status": "error", "message": "Equipment block not found (timeout 20s)"}

        # Extract HTML
        # We also might want the "Skins" part? The user said "Window with stuff".
        # .player-equipment usually contains the grid.
        # Let's clean it up slightly if needed (remove absolute positioning?)
        # For now, get raw HTML.

        # Extract CSS
        css_links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('link[rel="stylesheet"]'))
                .map(link => link.href);
        }""")

        element = await page.query_selector(selector)
        if not element:
            return {"status": "error", "message": "Element vanished"}

        html_content = await element.evaluate("el => el.outerHTML")

        # Post-process HTML: Fix relative links
        html_content = html_content.replace('src="/', 'src="https://pwobs.com/')
        html_content = html_content.replace('href="/', 'href="https://pwobs.com/')

        # Bundle CSS + JS + HTML
        full_html = ""
        for link in css_links:
            full_html += f'<link rel="stylesheet" href="{link}">\n'

        # CSS Overrides:
        # 1. transparent background
        # 2. overflow VISIBLE (was hidden) to allow tooltips
        # 3. Force Tooltips on hover (override opacity-0)
        # 4. Fix tooltip positioning (z-index)
        # 5. Add padding to body to prevent tooltip clipping at edges
        full_html += """
        <style>
            body { 
                background: transparent !important; 
                overflow: visible !important; 
                height: auto !important;
                min-height: 600px;
                /* Tooltips render UPWARDS/DOWNWARDS. 
                   We need padding, but less is okay if we scroll to center. */
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
                /* Ensure it's not cut off */
                position: absolute;
                background: rgba(0,0,0,0.95); /* Darker bg for readability */
                border: 1px solid #555;
                padding: 10px;
                border-radius: 5px;
                color: #fff;
                box-shadow: 0 5px 15px rgba(0,0,0,0.5);
                /* Reset possible hidden/overflow from parent */
            }
            
            /* Hide the "calendar/total refine" extras if they clutter */
            /* .player-equipment__bg + div { display: none; } */
        </style>
        <script>
            // Auto-scroll to center the equipment grid
            window.addEventListener("load", function() {
                const el = document.querySelector('.player-equipment');
                if(el) {
                    el.scrollIntoView({block: 'center', inline: 'center'});
                }
            });
        </script>
        """

        full_html += html_content

        # 3. Save to Cache
        # Refresh cache_entry to ensure we're not using a stale one if multiple scrapes happen (unlikely with Lock)
        # But we already have session from Depends, so let's just use it
        result = await session.execute(select(ObserverCache).filter_by(role_id=role_id))
        cache_entry = result.scalar_one_or_none()
        if not cache_entry:
            cache_entry = ObserverCache(role_id=role_id)
            session.add(cache_entry)
        
        cache_entry.html_content = full_html
        cache_entry.updated_at = get_msk_now()
        await session.commit()

        return {"status": "ok", "html": full_html, "source": "live"}

    except Exception as e:
        logging.error(f"Scrape error for {role_id}: {e}")
        return {"status": "error", "message": str(e)}

    finally:
        if page:
            await page.close()
