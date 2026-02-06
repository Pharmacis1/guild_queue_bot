import asyncio

from playwright.async_api import async_playwright

AUTH_FILE = "pwobs_auth.json"


async def main():
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("Navigating to login page...")
        await page.goto("https://pwobs.com/login")

        print("\n" + "=" * 50)
        print("ACTION REQUIRED:")
        print("1. Log in to PWOBS in the opened browser window.")
        print("2. Wait until you are redirected to your profile or main page.")
        print("3. Press ENTER in this console to save the session and exit.")
        print("=" * 50 + "\n")

        await asyncio.get_event_loop().run_in_executor(None, input, "")

        # Save state
        await context.storage_state(path=AUTH_FILE)
        print(f"\nSUCCESS! Auth state saved to '{AUTH_FILE}'.")
        print("You can now upload this file to your hosting server.")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
