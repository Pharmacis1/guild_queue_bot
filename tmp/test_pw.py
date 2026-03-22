import asyncio
from playwright.async_api import async_playwright

async def test():
    try:
        print("Starting playwright...")
        p = await async_playwright().start()
        print("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        print("Browser launched!")
        await browser.close()
        await p.stop()
        print("Done!")
    except Exception as e:
        import traceback
        print(f"Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
