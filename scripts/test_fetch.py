import asyncio

import aiosqlite
from playwright.async_api import async_playwright

# Configuration
TEST_DB = "test_archive.db"
TARGET_IDS = [20173460, 3651601, 2141194160]
BASE_URL = "https://pwobs.com/centaur/players/"

async def init_db():
    async with aiosqlite.connect(TEST_DB) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS test_players (
                role_id INTEGER PRIMARY KEY,
                nickname TEXT,
                class_name TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.commit()
    print(f"Database {TEST_DB} initialized.")

async def main():
    async with async_playwright() as p:
        # Launch browser in HEADED mode so user can see and interact
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("--- STEP 1: LOGIN ---")
        print("Navigating to login page...")
        await page.goto("https://pwobs.com/login")
        
        print("\n" + "="*50)
        print("ACTION REQUIRED: Please log in via Telegram/VK in the browser window.")
        print("Once you are logged in and see your profile or the main page,")
        print("Press ENTER in this console to continue...")
        print("="*50 + "\n")
        
        # Wait for user input in console
        await asyncio.get_event_loop().run_in_executor(None, input, "")
        
        print("Continuing with scraping...")

        async with aiosqlite.connect(TEST_DB) as conn:
            for role_id in TARGET_IDS:
                url = f"{BASE_URL}{role_id}"
                print(f"Processing ID {role_id}: {url}")
                
                try:
                    await page.goto(url)
                    # Wait for network idle to ensure content loads
                    await page.wait_for_load_state("networkidle")
                    
                    # Try to find elements. 
                    # Note: Selectors need to be discovered. 
                    # Usually PWOBS puts name in h1 or similar.
                    # We will dump the text content of likely containers if uncertain.
                    
                    # Attempt 1: Look for common profile headers
                    # Adjust these selectors based on actual page structure if needed.
                    
                    # Assuming standard bootstrap or similar structure
                    # We'll try to get the page title or specific meta tags first
                    
                    title = await page.title()
                    content_text = await page.content()
                    
                    # Simple heuristic extraction if selectors are unknown (first run)
                    # We will try to find the nickname in standard locations
                    
                    # Let's try to get h1 or class info
                    # Based on typical detail pages
                    nickname_el = await page.query_selector("h1")
                    class_el = await page.query_selector(".class-icon") # Example selector
                    
                    nickname = await nickname_el.text_content() if nickname_el else "Unknown"
                    
                    # If specific classes are used, might need better selectors.
                    # For now, let's grab the H1 and maybe some other text
                    
                    # Let's try to grab all text and extract roughly
                    body_text = await page.inner_text("body")
                    
                    # Placeholder validation
                    if "Login" in title or "Вход" in title:
                        print(f"WARNING: Still redirected to login for {role_id}. Auth might have failed/expired.")
                        continue

                    # Attempt to extract data
                    # Valid PWOBS profile usually has Name and Class prominently
                    # We will save what we find
                    
                    print(f"  -> Title: {title}")
                    print(f"  -> Found H1: {nickname}")
                    
                    # Save to DB
                    await conn.execute("""
                        INSERT OR REPLACE INTO test_players (role_id, nickname, class_name)
                        VALUES (?, ?, ?)
                    """, (role_id, nickname.strip(), title.strip()))
                    await conn.commit()
                    print("  -> Saved to DB.")
                    
                except Exception as e:
                    print(f"Error processing {role_id}: {e}")
                
                # Sleep briefly to be polite
                await asyncio.sleep(2)

        print("\nDone! Check test_archive.db")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(init_db())
    asyncio.run(main())
