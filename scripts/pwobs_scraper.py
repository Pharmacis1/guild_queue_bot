import argparse
import asyncio
import logging
import os
import sys

# Add parent directory to path to allow importing database
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from database import AsyncSessionLocal, Player, select, update
from consts import CLASS_BY_NAME

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("pwobs_scraper")

BASE_URL_TEMPLATE = "https://pwobs.com/{server}/players/{role_id}"
AUTH_FILE = "pwobs_auth.json"

async def get_target_players(session, only_unknown=False):
    """Fetches list of (role_id) for players currently in clan."""
    if only_unknown:
        # Check players in clan AND without nickname or class
        # Assuming ID -1 or nickname is NULL/empty
        stmt = select(Player.role_id, Player.nickname, Player.class_id).filter(
            Player.in_clan == 1,
            (Player.nickname == None) | (Player.nickname == "") | (Player.class_id == -1)
        )
        result = await session.execute(stmt)
        rows = result.all()
        
        if rows:
            logger.info(f"Selected {len(rows)} players for scraping details:")
            for r in rows[:5]:  # Log first 5 to avoid spam
                logger.info(f"  - ID {r[0]}: Nick={r[1]}, Class={r[2]}")
        return [r[0] for r in rows]
    else:
        stmt = select(Player.role_id).filter(Player.in_clan == 1)
        result = await session.execute(stmt)
        return [r[0] for r in result.scalars().all()]

async def run_scraper(server="capella", dry_run=False, headless=True, only_unknown=False):
    """
    Runs the scraper.
    """
    logger.info(f"Starting PWOBS scraper for server: {server} (Headless: {headless}, Only Unknown: {only_unknown})")
    stats = {"processed": 0, "updated": 0, "errors": 0}

    from playwright.async_api import async_playwright

    async with AsyncSessionLocal() as session:
        target_ids = await get_target_players(session, only_unknown=only_unknown)
        logger.info(f"Found {len(target_ids)} players to check.")

        if not target_ids:
            return stats

        async with async_playwright() as p:
            context_args = {}
            if os.path.exists(AUTH_FILE):
                try:
                    with open(AUTH_FILE, "r", encoding="utf-8") as f:
                        if f.read().strip():
                            context_args["storage_state"] = AUTH_FILE
                            logger.info(f"Loading auth state from {AUTH_FILE}")
                except Exception as e:
                    logger.error(f"Error checking auth file: {e}")

            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(**context_args)
            page = await context.new_page()

            # Check login
            try:
                await page.goto("https://pwobs.com/profile", wait_until="domcontentloaded")
                title = await page.title()
                if "login" in page.url or any(x in title for x in ["Вход", "Login", "Авторизация"]):
                    if not headless:
                        logger.info("Manual login required...")
                        await page.goto("https://pwobs.com/login")
                        print("\nACTION REQUIRED: Log in to PWOBS and press ENTER when done...")
                        await asyncio.get_event_loop().run_in_executor(None, input, "")
                        await context.storage_state(path=AUTH_FILE)
                        logger.info(f"Auth state saved to {AUTH_FILE}")
                    else:
                        logger.warning("Session invalid! Headless mode cannot perform login.")
                        await page.screenshot(path="login_failed_bg.png")
                        await browser.close()
                        return stats
            except Exception as e:
                logger.warning(f"Initial login check failed: {e}")

            for role_id in target_ids:
                url = BASE_URL_TEMPLATE.format(server=server, role_id=role_id)
                logger.info(f"Checking ID {role_id}: {url}")
                stats["processed"] += 1

                try:
                    # Use domcontentloaded to avoid heavy tracking scripts timeout
                    await page.goto(url, wait_until="domcontentloaded")
                    
                    # Wait for items to ensure data is rendered
                    try:
                        await page.wait_for_selector(".player-equipment__item", timeout=10000)
                    except:
                        pass
                    
                    title = await page.title()
                    if "404" in title or "Page not found" in title:
                        logger.warning(f"Player {role_id} not found.")
                        continue

                    nickname_el = await page.query_selector("h1")
                    if not nickname_el:
                        continue

                    nickname = (await nickname_el.text_content()).strip()
                    found_class_id = -1

                    search_keys = sorted([k for k in CLASS_BY_NAME.keys() if not k.isdigit()], key=len, reverse=True)
                    title_lower = title.lower()
                    for cname_key in search_keys:
                        if cname_key in title_lower:
                            found_class_id = CLASS_BY_NAME[cname_key]
                            logger.info(f"  -> Found in Title: {nickname} ({found_class_id})")
                            break

                    if found_class_id == -1:
                        body_text = await page.inner_text("body")
                        body_lower = body_text.lower()
                        for cname_key in search_keys:
                            if cname_key in body_lower:
                                found_class_id = CLASS_BY_NAME[cname_key]
                                logger.info(f"  -> Found in Body: {nickname} ({found_class_id})")
                                break

                    if not dry_run:
                        stmt_upd = update(Player).where(Player.role_id == role_id).values(nickname=nickname, class_id=found_class_id)
                        await session.execute(stmt_upd)
                        await session.commit()
                        logger.info("  -> Saved.")
                        stats["updated"] += 1

                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Error processing {role_id}: {e}")
                    stats["errors"] += 1

            if not headless:
                await context.storage_state(path=AUTH_FILE)

            await browser.close()

    logger.info(f"Scraping completed: {stats}")
    return stats

async def main(server, dry_run=False, only_unknown=False):
    await run_scraper(server, dry_run, headless=False, only_unknown=only_unknown)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PWOBS Scraper")
    parser.add_argument("--server", type=str, default="capella", help="Server name")
    parser.add_argument("--dry-run", action="store_true", help="Do not save changes")
    parser.add_argument("--only-unknown", action="store_true", help="Only missing info")
    args = parser.parse_args()
    asyncio.run(main(args.server, args.dry_run, args.only_unknown))
