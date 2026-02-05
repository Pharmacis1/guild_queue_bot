import logging
from typing import Optional

import httpx


async def get_telegram_avatar_url(telegram_id: int, bot_token: str) -> Optional[str]:
    """
    Fetch user's Telegram profile photo URL using Bot API.
    Returns the file URL or None if no photo exists.
    """
    try:
        # Get user profile photos
        url = f"https://api.telegram.org/bot{bot_token}/getUserProfilePhotos"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params={
                "user_id": telegram_id,
                "limit": 1
            })
            
            if response.status_code != 200:
                logging.error(f"Failed to get profile photos: {response.text}")
                return None
                
            data = response.json()
            
            if not data.get("ok") or not data["result"].get("photos"):
                return None
                
            # Get the first photo's file_id (smallest size for avatar)
            photo = data["result"]["photos"][0][0]  # First photo, smallest size
            file_id = photo["file_id"]
            
            # Get file path
            file_url = f"https://api.telegram.org/bot{bot_token}/getFile"
            file_response = await client.get(file_url, params={"file_id": file_id})
            
            if file_response.status_code != 200:
                logging.error(f"Failed to get file path: {file_response.text}")
                return None
                
            file_data = file_response.json()
            
            if not file_data.get("ok"):
                return None
                
            file_path = file_data["result"]["file_path"]
            
            # Construct full URL
            avatar_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
            return avatar_url
            
    except Exception as e:
        logging.error(f"Error fetching avatar for user {telegram_id}: {e}")
        return None
