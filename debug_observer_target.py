import asyncio
from playwright.async_api import async_playwright
import os

# ID for 拉格雷克雷
ROLE_ID = 445777
SERVER = "capella"
URL = f"https://pwobs.com/{SERVER}/players/{ROLE_ID}"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context_args = {
             "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
             "viewport": {"width": 1280, "height": 720}
        }
        if os.path.exists("pwobs_auth.json"):
            print("Loading auth...")
            context_args["storage_state"] = "pwobs_auth.json"

        context = await browser.new_context(**context_args)
        page = await context.new_page()
        
        print(f"Navigating to {URL}...")
        try:
            # Main load
            await page.goto(URL, timeout=30000)
            
            # Selector check
            selector = ".player-equipment"
            print(f"Waiting for selector: {selector}")
            
            # Try 5s first (to reproduce failure)
            try:
                await page.wait_for_selector(selector, timeout=5000)
                print("SUCCESS: Found selector in < 5s")
            except Exception as e:
                print(f"FAIL: Not found in 5s: {e}")
                print("Trying longer wait (20s)...")
                try:
                    await page.wait_for_selector(selector, timeout=20000)
                    print("SUCCESS: Found selector in extended wait")
                except Exception as e2:
                    print(f"FAIL: Not found in 20s either: {e2}")
            
            # Dump HTML for inspection regardless
            content = await page.content()
            with open(f"debug_{ROLE_ID}.html", "w", encoding="utf-8") as f:
                f.write(content)
                
        except Exception as e:
            print(f"Global Error: {e}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
