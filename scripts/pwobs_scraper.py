import asyncio
import aiosqlite
import argparse
from playwright.async_api import async_playwright
import logging
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from consts import CLASS_BY_NAME

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("pwobs_scraper")

DB_NAME = "guild_bot.db"
BASE_URL_TEMPLATE = "https://pwobs.com/{server}/players/{role_id}"

async def get_target_players(conn, only_unknown=False):
    """Fetches list of (role_id) for players currently in clan."""
    if only_unknown:
        # Check players in clan AND without nickname or class
        # Assuming ID 0/1 are valid classes, checking if class_id is -1 or nickname is NULL
        async with conn.execute("SELECT role_id, nickname, class_id FROM players WHERE in_clan = 1 AND (nickname IS NULL OR class_id = -1)") as cursor:
            rows = await cursor.fetchall()
            # Debug logging to see why they were selected
            if rows:
                logger.info(f"Selected {len(rows)} players for scraping details:")
                for r in rows[:5]: # Log first 5 to avoid spam
                     logger.info(f"  - ID {r[0]}: Nick={r[1]}, Class={r[2]}")
            return [r[0] for r in rows]
    else:
        async with conn.execute("SELECT role_id FROM players WHERE in_clan = 1") as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

async def update_player(conn, role_id, nickname, class_id):
    """Updates player info in database."""
    await conn.execute("""
        UPDATE players 
        SET nickname = ?, class_id = ? 
        WHERE role_id = ?
    """, (nickname, class_id, role_id))
    await conn.commit()


AUTH_FILE = "pwobs_auth.json"

async def run_scraper(server="capella", dry_run=False, headless=True, only_unknown=False):
    """
    Runs the scraper.
    :param headless: If False, shows browser (for initial login).
    :param only_unknown: If True, checks only players with missing nickname/class.
    """
    logger.info(f"Starting PWOBS scraper for server: {server} (Headless: {headless}, Only Unknown: {only_unknown})")
    stats = {"processed": 0, "updated": 0, "errors": 0}
    
    async with aiosqlite.connect(DB_NAME) as conn:
        target_ids = await get_target_players(conn, only_unknown=only_unknown)
        logger.info(f"Found {len(target_ids)} players to check.")
        
        if not target_ids:
            return stats

        async with async_playwright() as p:
            # Try to load storage state
            context_args = {}
            import os
            if os.path.exists(AUTH_FILE):
                try:
                    with open(AUTH_FILE, 'r', encoding='utf-8') as f:
                        if f.read().strip(): # Check if not empty
                            # Basic check, Playwright might still complain if invalid JSON but we try
                            context_args["storage_state"] = AUTH_FILE
                            logger.info(f"Loading auth state from {AUTH_FILE}")
                        else:
                            logger.warning(f"Auth file {AUTH_FILE} is empty, ignoring.")
                except Exception as e:
                    logger.error(f"Error checking auth file: {e}")
            
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(**context_args)
            page = await context.new_page()

            # Navigate to base to check login
            try:
                await page.goto("https://pwobs.com/profile")
                # If redirected to login, we are not logged in
                if "login" in page.url:
                    if not headless:
                        logger.info("Navigate to login page...")
                        await page.goto("https://pwobs.com/login")
                        
                        print("\n" + "="*50)
                        print("ACTION REQUIRED: Log in to PWOBS in the browser.")
                        print("Press ENTER in this console when ready to proceed...")
                        print("="*50 + "\n")
                        await asyncio.get_event_loop().run_in_executor(None, input, "")
                        
                        # Save state after manual login
                        await context.storage_state(path=AUTH_FILE)
                        logger.info(f"Auth state saved to {AUTH_FILE}")
                    else:
                        logger.warning("Session invalid! Redirected to login in headless mode.")
                        await page.screenshot(path="login_failed.png")
                        logger.info("Screenshot saved to login_failed.png")


            except Exception as e:
                logger.warning(f"Initial check failed: {e}")

            for role_id in target_ids:
                url = BASE_URL_TEMPLATE.format(server=server, role_id=role_id)
                logger.info(f"Checking ID {role_id}: {url}")
                stats["processed"] += 1
                
                try:
                    await page.goto(url)
                    await page.wait_for_load_state("networkidle")
                    
                    # Check for 404/Not Found
                    title = await page.title()
                    if "404" in title or "Page not found" in title:
                        logger.warning(f"Player {role_id} not found on PWOBS (404).")
                        # Do NOT mark as -2, user wants to retry next time.
                        continue

                # Basic Scrape Strategy
                    # 1. Nickname usually in h1
                    nickname_el = await page.query_selector("h1")
                    if not nickname_el:
                        logger.warning(f"Could not find H1 for {role_id}. Skipping.")
                        continue
                        
                    nickname = await nickname_el.text_content()
                    nickname = nickname.strip()
                    
                    found_class_id = -1
                    
                    # Filter out digit-only keys (like "0", "1") to avoid matching dates/stats
                    # Sort by length descending to match "Duskblade" before "Blade" (example)
                    search_keys = sorted(
                        [k for k in CLASS_BY_NAME.keys() if not k.isdigit()],
                        key=len,
                        reverse=True
                    )
                    
                    # 2. Class - Try Title First (Most Accurate)
                    title_lower = title.lower()
                    for cname_key in search_keys:
                        if cname_key in title_lower:
                            found_class_id = CLASS_BY_NAME[cname_key]
                            logger.info(f"  -> Found in Title: {nickname} (Class ID: {found_class_id})")
                            break
                    
                    # 3. Class - Fallback to Body (Riskier)
                    if found_class_id == -1:
                        body_text = await page.inner_text("body")
                        body_lower = body_text.lower()
                        
                        for cname_key in search_keys:
                            if cname_key in body_lower:
                                found_class_id = CLASS_BY_NAME[cname_key]
                                logger.info(f"  -> Found in Body: {nickname} (Class ID: {found_class_id})")
                                break
                    
                    if found_class_id == -1:
                        logger.warning(f"  -> Class not found for {nickname}")


                    
                    if not dry_run:
                        await update_player(conn, role_id, nickname, found_class_id)
                        logger.info("  -> Saved.")
                        stats["updated"] += 1
                    else:
                        logger.info("  -> Dry run: skipped save.")
                        
                    await asyncio.sleep(2) # Polite delay

                except Exception as e:
                    logger.error(f"Error processing {role_id}: {e}")
                    stats["errors"] += 1

            # Always save state if running interactively (setup mode)
            if not headless:
                await context.storage_state(path=AUTH_FILE)
                logger.info(f"Auth state saved to {AUTH_FILE}")

            await browser.close()
    
    logger.info("Scraping completed.")
    return stats

async def main(server, dry_run=False, only_unknown=False):
    # wrapper for direct run
    # If running directly, we default to headless=False to allow login
    await run_scraper(server, dry_run, headless=False, only_unknown=only_unknown)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='PWOBS Scraper')
    parser.add_argument('--server', type=str, default='capella', help='Server name (subdomain)')
    parser.add_argument('--dry-run', action='store_true', help='Do not save changes to DB')
    parser.add_argument('--only-unknown', action='store_true', help='Only check players without detailed info')
    
    args = parser.parse_args()
    asyncio.run(main(args.server, args.dry_run, args.only_unknown))
