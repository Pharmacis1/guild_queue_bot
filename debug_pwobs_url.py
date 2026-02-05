import asyncio

import aiohttp


async def check_url(url):
    print(f"Checking {url}...")
    async with aiohttp.ClientSession() as session:
        async with session.get(url, allow_redirects=True) as resp:
            print(f"Status: {resp.status}")
            print(f"Final URL: {resp.url}")
            text = await resp.text()
            if "Ригель" in text:
                print("Found 'Ригель' in content")
            else:
                print("Not found")

async def main():
    # Attempt 1: Search URL format (Guessing)
    await check_url("https://pwobs.com/search?name=Ригель&server=capella")
    
    # Attempt 2: Direct URL format (Guessing based on typical SEO)
    await check_url("https://pwobs.com/u/Ridgel") # Just guessing
    
    # Attempt 3: Search with POST?
    # Actually, let's look at the home page or headers again if needed.
    # But wait, the user's HTML usually has the canonical URL. 
    # Let me check the provided HTML again for any hints on URL structure.

if __name__ == "__main__":
    asyncio.run(main())
