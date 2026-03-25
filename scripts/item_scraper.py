import asyncio
import logging
import os
import sys

import aiohttp
from bs4 import BeautifulSoup

# Add parent directory to path to allow importing database
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from database import AsyncSessionLocal, Item, select

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("item_scraper")

BASE_URL_TEMPLATE = "https://www.pwdatabase.com/ru/items/{item_id}"

async def fetch_item_name(session, item_id):
    """
    Fetches the item name from pwdatabase.com.
    Returns (item_id, name) tuple. Name is None if not found or error.
    """
    url = BASE_URL_TEMPLATE.format(item_id=item_id)
    try:
        async with session.get(url, timeout=30) as response:
            if response.status == 404:
                return item_id, None

            if response.status != 200:
                logger.warning(f"Failed to fetch {item_id}: Status {response.status}")
                return item_id, None

            content = await response.read()

            try:
                html = content.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    html = content.decode("windows-1251")
                except UnicodeDecodeError:
                    html = content.decode("windows-1251", errors="replace")

            soup = BeautifulSoup(html, "html.parser")

            # 1. Try th.item-name
            name_el = soup.select_one("th.item-name")
            if name_el:
                name = name_el.get_text(strip=True)
                if name and "Perfect World" not in name:
                    return item_id, name

            # 2. Try td.item-name
            name_el = soup.select_one("td.item-name")
            if name_el:
                name = name_el.get_text(strip=True)
                if name and "Perfect World" not in name:
                    return item_id, name

            # 3. Try h1
            h1 = soup.select_one("h1")
            if h1:
                name = h1.get_text(strip=True)
                if name and "Perfect World" not in name:
                    return item_id, name

            # 4. Fallback: Parse Title
            if soup.title and soup.title.string:
                title_text = soup.title.string
                if " - " in title_text:
                    name = title_text.split(" - ")[-1].strip()
                    if name and name != "Perfect World Item Database":
                        return item_id, name

            return item_id, None

    except Exception as e:
        logger.error(f"Error fetching item {item_id}: {e}")
        return item_id, None

async def run_item_scraper(item_ids):
    """
    Scrapes names for the given list of item IDs and updates the database.
    """
    if not item_ids:
        return

    logger.info(f"Starting item scraper for {len(item_ids)} items: {item_ids}")

    async with AsyncSessionLocal() as db_session:
        async with aiohttp.ClientSession() as http_session:
            tasks = []
            for item_id in item_ids:
                tasks.append(fetch_item_name(http_session, item_id))

            results = await asyncio.gather(*tasks)

            for item_id, name in results:
                if name:
                    logger.info(f"Found name for {item_id}: {name}")
                    # Use merge to insert or update
                    item_obj = await db_session.get(Item, item_id)
                    if not item_obj:
                        item_obj = Item(id=item_id, name=name)
                        db_session.add(item_obj)
                    else:
                        item_obj.name = name
                else:
                    logger.warning(f"Could not find name for item {item_id}")

            await db_session.commit()

    logger.info("Item scraping completed.")

if __name__ == "__main__":
    async def main():
        print("Checking database for missing item names...")
        from database import Event
        async with AsyncSessionLocal() as session:
            # 1. Get all item IDs from events (event_type 0 = Item Drop/Consumption?)
            # Assuming event_type depends on project logic.
            stmt = select(Event.value).where(Event.event_type == 0).distinct()
            result = await session.execute(stmt)
            all_item_ids = set(result.scalars().all())

            # 2. Get already scraped items
            stmt_items = select(Item.id)
            result_items = await session.execute(stmt_items)
            known_ids = set(result_items.scalars().all())

            missing = list(all_item_ids - known_ids)
            print(f"Total item events: {len(all_item_ids)}")
            print(f"Known items: {len(known_ids)}")
            print(f"Missing items to scrape: {len(missing)}")

            if missing:
                await run_item_scraper(missing)
            else:
                print("All items are already scraped.")

    asyncio.run(main())
