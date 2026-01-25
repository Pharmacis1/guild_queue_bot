from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import logging
import os
import secrets
from pydantic import BaseModel
from typing import Optional
from auth_helper import validate_init_data, validate_widget_auth
from avatar_helper import get_telegram_avatar_url
import aiosqlite
from web_database import DB_NAME

router = APIRouter()
templates = Jinja2Templates(directory="templates")

BOT_TOKEN = os.getenv("BOT_TOKEN")

class LoginRequest(BaseModel):
    initData: str

class WidgetLoginRequest(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str
    
@router.get("/login/telegram")
async def login_telegram_redirect(request: Request):
    """
    Handle the redirect from Telegram Login Widget.
    It returns query params: id, first_name, username, photo_url, auth_date, hash
    """
    params = dict(request.query_params)
    logging.info(f"Telegram Redirect params: {params}")
    
    if not BOT_TOKEN:
         return templates.TemplateResponse("login.html", {"request": request, "error_message": "Server Config Error"})

    try:
         validate_widget_auth(params.copy(), BOT_TOKEN)
         
         tg_id = int(params.get('id'))
         
         # Check DB
         async with aiosqlite.connect(DB_NAME) as conn:
            cursor = await conn.execute("SELECT id FROM users WHERE telegram_id = ?", (tg_id,))
            user_row = await cursor.fetchone()
            
            if not user_row:
                 # Optional: Create user on fly? Or reject.
                 # Policy: Reject if not in DB (must start bot first)
                 # Actually, for better UX, maybe just show error page or redirect to index with error.
                 # For now, let's redirect to index and let index handle 'not authenticated' look but maybe flash a message?
                 # Since we use session, we just won't set the session.
                 return RedirectResponse(url="/?error=not_registered")

            # Update Avatar
            avatar_url = params.get('photo_url')
            if avatar_url:
                await conn.execute("UPDATE users SET avatar_url = ? WHERE telegram_id = ?", (avatar_url, tg_id))
                await conn.commit()
         
         request.session['user_id'] = tg_id
         return RedirectResponse(url="/")
         
    except Exception as e:
        logging.error(f"Redirect Login Failed: {e}")
        return RedirectResponse(url="/?error=auth_failed")

@router.post("/api/login")
async def login(data: LoginRequest, request: Request, response: Response):
    logging.info("Auth attempt received (WebApp)")
    
    if not BOT_TOKEN:
        logging.error("No BOT_TOKEN")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Server Config Error (No Token)"})
    
    try:
        # 1. Validate Initial Data
        parsed = validate_init_data(data.initData, BOT_TOKEN)
        user_data = parsed.get("user")
        
        logging.info(f"Auth data valid. User: {user_data}")
        
        if not user_data:
            return JSONResponse(status_code=400, content={"status": "error", "message": "No user data"})
            
        tg_id = user_data['id']
        
        # 2. Check Database
        async with aiosqlite.connect(DB_NAME) as conn:
            cursor = await conn.execute("SELECT id FROM users WHERE telegram_id = ?", (tg_id,))
            user_row = await cursor.fetchone()
            
            if not user_row:
                 return JSONResponse(status_code=403, content={"status": "error", "message": "Вы не зарегистрированы в боте. Нажмите /start в боте."})
            
            user_db_id = user_row[0]
            
            cursor = await conn.execute("SELECT count(*) FROM characters WHERE user_id = ?", (user_db_id,))
            char_count = (await cursor.fetchone())[0]
            
            if char_count == 0:
                 return JSONResponse(status_code=403, content={"status": "error", "message": "У вас нет персонажей в гильдии."})
            
            # Fetch and update avatar
            avatar_url = await get_telegram_avatar_url(tg_id, BOT_TOKEN)
            if avatar_url:
                await conn.execute("UPDATE users SET avatar_url = ? WHERE telegram_id = ?", (avatar_url, tg_id))
                await conn.commit()

        # 3. Success
        request.session['user_id'] = tg_id
        return {"status": "ok", "message": "Logged in"}

    except ValueError as ve:
        return JSONResponse(status_code=403, content={"status": "error", "message": f"Auth failed: {str(ve)}"})
    except Exception as e:
        logging.error(f"Login error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Internal error"})

@router.post("/api/login/widget")
async def login_widget(data: WidgetLoginRequest, request: Request):
    logging.info("Auth attempt received (Widget)")
    
    if not BOT_TOKEN:
        return JSONResponse(status_code=500, content={"status": "error", "message": "Server Config Error"})
        
    try:
        # Convert Pydantic model to dict, excluding None defaults if they weren't in original payload?
        # Actually validation needs exact payload. Pydantic might add defaults.
        # But for receiving data, we just need to ensure we validate what we received.
        # Let's trust that the frontend sends exactly what the widget gave.
        # The validation function expects a dict.
        
        data_dict = data.dict(exclude_none=True)
        # Note: 'id' might be int, validation needs to handle it or convert to string for string construction?
        # The validation string construction `f"{key}={value}"` handles int->str conversion correctly.
        
        validate_widget_auth(data_dict.copy(), BOT_TOKEN)
        
        tg_id = data.id
        logging.info(f"Widget auth valid for ID: {tg_id}")
        
        # Check specific user requirements (optional, but good for consistency)
        async with aiosqlite.connect(DB_NAME) as conn:
            cursor = await conn.execute("SELECT id FROM users WHERE telegram_id = ?", (tg_id,))
            user_row = await cursor.fetchone()
            
            if not user_row:
                 return JSONResponse(status_code=403, content={"status": "error", "message": "Вы не зарегистрированы в боте. Нажмите /start в боте."})
            
            # Use widget photo_url if available, otherwise fetch from API
            avatar_url = data.photo_url
            if not avatar_url:
                avatar_url = await get_telegram_avatar_url(tg_id, BOT_TOKEN)
            
            if avatar_url:
                await conn.execute("UPDATE users SET avatar_url = ? WHERE telegram_id = ?", (avatar_url, tg_id))
                await conn.commit()
            
        request.session['user_id'] = tg_id
        return {"status": "ok", "message": "Logged in"}
        
    except ValueError as ve:
        return JSONResponse(status_code=403, content={"status": "error", "message": f"Auth failed: {str(ve)}"})
    except Exception as e:
        logging.error(f"Widget login error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Internal error"})

@router.post("/api/logout")
async def logout(request: Request):
    request.session.pop('user_id', None)
    return {"status": "ok", "message": "Logged out"}
