import asyncio
import logging
import os
import sys

import aiohttp
import aiosqlite
from bs4 import BeautifulSoup

# Add parent directory to path to allow importing database
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# from database import DB_NAME
DB_NAME = "guild_bot.db"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("item_scraper")

BASE_URL_TEMPLATE = "https://www.pwdatabase.com/ru/items/{item_id}"

async def fetch_item_name(session, item_id):
    """
    Fetches the item name from pwdatabase.com.
    Returns (item_id, name) tuple. Name is None if not found or error.
    """
    url = BASE_URL_TEMPLATE.format(item_id=item_id)
    try:
        async with session.get(url) as response:
            if response.status == 404:
                return item_id, None
            
            if response.status != 200:
                logger.warning(f"Failed to fetch {item_id}: Status {response.status}")
                return item_id, None
            
            # Read as binary to handle encoding manually
            content = await response.read()
            
            # Try decoding as utf-8 first (standard)
            try:
                html = content.decode('utf-8')
            except UnicodeDecodeError:
                # Fallback to windows-1251 if utf-8 fails
                try:
                    html = content.decode('windows-1251')
                except UnicodeDecodeError:
                    # Final fallback with replace
                    html = content.decode('windows-1251', errors='replace')

            soup = BeautifulSoup(html, 'html.parser')
            
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

            # 3. Try h1 (less reliable)
            h1 = soup.select_one("h1")
            if h1:
                name = h1.get_text(strip=True)
                if name and "Perfect World" not in name:
                    return item_id, name

            # 4. Fallback: Parse Title "Perfect World Item Database - Item Name"
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
    
    async with aiosqlite.connect(DB_NAME) as conn:
        async with aiohttp.ClientSession() as session:
            tasks = []
            for item_id in item_ids:
                tasks.append(fetch_item_name(session, item_id))
                
            results = await asyncio.gather(*tasks)
            
            for item_id, name in results:
                if name:
                    logger.info(f"Found name for {item_id}: {name}")
                    # Insert or replace
                    await conn.execute("INSERT OR REPLACE INTO items (id, name) VALUES (?, ?)", (item_id, name))
                else:
                    logger.warning(f"Could not find name for item {item_id}")
                    # Optionally insert a placeholder or do nothing
            
            await conn.commit()
            
    logger.info("Item scraping completed.")

if __name__ == "__main__":
    async def main():
        print("Checking database for missing item names...")
        async with aiosqlite.connect(DB_NAME) as conn:
            # 1. Get all item IDs from events
            async with conn.execute("SELECT DISTINCT value FROM events WHERE event_type = 0") as cursor:
                rows = await cursor.fetchall()
                all_item_ids = {r[0] for r in rows}
            
            # 2. Get already scraped items
            async with conn.execute("SELECT id FROM items") as cursor:
                rows = await cursor.fetchall()
                known_ids = {r[0] for r in rows}
            
            missing = list(all_item_ids - known_ids)
            print(f"Total item events: {len(all_item_ids)}")
            print(f"Known items: {len(known_ids)}")
            print(f"Missing items to scrape: {len(missing)}")
            
            if missing:
                await run_item_scraper(missing)
            else:
                print("All items are already scraped.")

    asyncio.run(main())
