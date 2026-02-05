import asyncio

from playwright.async_api import async_playwright


async def debug_pwobs():
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
             viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        
        # known valid ID
        url = "https://pwobs.com/capella/players/4208"
        print(f"Navigating to {url}...")
        
        await page.goto(url)
        
        # Wait a bit to see what happens
        print("Waiting 10s...")
        await asyncio.sleep(10)
        
        title = await page.title()
        print(f"Page Title: {title}")
        
        # Screenshot
        await page.screenshot(path="debug_pwobs_4208.png")
        print("Saved screenshot to debug_pwobs_4208.png")
        
        # HTML
        content = await page.content()
        with open("debug_pwobs_4208.html", "w", encoding="utf-8") as f:
            f.write(content)
        print("Saved HTML to debug_pwobs_4208.html")
        
        if "player-equipment" in content:
            print("SUCCESS: Found .player-equipment in HTML")
        else:
            print("FAILURE: .player-equipment NOT found")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_pwobs())
