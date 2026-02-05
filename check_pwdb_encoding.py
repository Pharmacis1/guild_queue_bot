import asyncio

import aiohttp


async def check_encoding():
    url = "https://www.pwdatabase.com/ru/items/58682"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            print(f"URL: {url}")
            print(f"Status: {response.status}")
            print(f"Headers: {response.headers}")
            print(f"Charset in Content-Type: {response.charset}")
            
            # Read as bytes
            content = await response.read()
            # Try decoding as utf-8
            try:
                text_utf8 = content.decode('utf-8')
                print("Decoded as UTF-8 successfully.")
                if "Камень Тайхао" in text_utf8:
                     print("Found 'Камень Тайхао' in UTF-8.")
            except UnicodeDecodeError:
                print("Failed to decode as UTF-8.")
                
            # Try decoding as windows-1251
            try:
                text_1251 = content.decode('windows-1251')
                print("Decoded as Windows-1251 successfully.")
                if "Камень Тайхао" in text_1251:
                     print("Found 'Камень Тайхао' in Windows-1251.")
            except UnicodeDecodeError:
                print("Failed to decode as Windows-1251.")

asyncio.run(check_encoding())
