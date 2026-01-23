import aiohttp
import asyncio
from bs4 import BeautifulSoup

async def main():
    item_id = 48669
    url = f"https://www.pwdatabase.com/ru/items/{item_id}"
    print(f"Fetching {url}...")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            print(f"Status: {response.status}")
            html = await response.text(encoding='windows-1251', errors='replace')
            
            soup = BeautifulSoup(html, 'html.parser')
            
            print(f"Title: {soup.title.string if soup.title else 'No title'}")
            
            # Find ANY element with class 'item-name' or 'name'
            for tag in soup.find_all(class_=lambda c: c and ('name' in c or 'Name' in c)):
                print(f"Tag with *name* class: <{tag.name} class='{tag.get('class')}'>{tag.get_text(strip=True)[:50]}...")
            
            # Print first 2000 chars
            print(f"Body snippet: {soup.body.get_text()[:2000] if soup.body else 'No body'}")

if __name__ == "__main__":
    asyncio.run(main())
