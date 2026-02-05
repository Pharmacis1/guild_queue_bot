import asyncio
import os

from playwright.async_api import async_playwright

AUTH_FILE = "pwobs_auth.json"
URL = "https://pwobs.com/capella/players/4208"

async def main():
    async with async_playwright() as p:
        context_args = {}
        if os.path.exists(AUTH_FILE):
             context_args["storage_state"] = AUTH_FILE
             
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(**context_args)
        page = await context.new_page()
        
        print(f"Navigating to {URL}...")
        await page.goto(URL)
        await page.wait_for_load_state("networkidle")
        
        content = await page.content()
        with open("pwobs_4208.html", "w", encoding="utf-8") as f:
            f.write(content)
            
        text = await page.inner_text("body")
        with open("pwobs_4208.txt", "w", encoding="utf-8") as f:
            f.write(text)
            
        print("Use view_file to check pwobs_4208.html and pwobs_4208.txt")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
