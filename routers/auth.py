import logging
import os
from typing import Optional

from fastapi import APIRouter, Request, Response, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from auth_helper import validate_init_data, validate_widget_auth
from avatar_helper import get_telegram_avatar_url
from database import AsyncSessionLocal, User, Character

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
        tg_id = int(params.get("id"))

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).filter_by(telegram_id=tg_id))
            user = result.scalar_one_or_none()

            if not user:
                return RedirectResponse(url="/?error=not_registered")

            # Update Avatar
            avatar_url = params.get("photo_url")
            if avatar_url:
                user.avatar_url = avatar_url
                await session.commit()

        request.session["user_id"] = tg_id
        logging.info(f"SETTING SESSION USER_ID: {tg_id}")
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

        tg_id = user_data["id"]

        # 2. Check Database
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).filter_by(telegram_id=tg_id))
            user = result.scalar_one_or_none()

            if not user:
                return JSONResponse(
                    status_code=403,
                    content={"status": "error", "message": "Вы не зарегистрированы в боте. Нажмите /start в боте."},
                )

            result = await session.execute(select(func.count(Character.id)).filter_by(user_id=user.id))
            char_count = result.scalar()

            # For TMA, we allow login even with 0 characters so they can link themselves
            if char_count == 0:
                # We can check a flag or just allow it if initData was provided (TMA)
                logging.info(f"User {tg_id} has 0 chars but allowing login via TMA.")

            # Fetch and update avatar
            avatar_url = await get_telegram_avatar_url(tg_id, BOT_TOKEN)
            if avatar_url:
                user.avatar_url = avatar_url
                await session.commit()

        # 3. Success
        request.session["user_id"] = tg_id
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
        data_dict = data.model_dump(exclude_none=True)
        validate_widget_auth(data_dict.copy(), BOT_TOKEN)

        tg_id = data.id
        logging.info(f"Widget auth valid for ID: {tg_id}")

        # Check specific user requirements
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).filter_by(telegram_id=tg_id))
            user = result.scalar_one_or_none()

            if not user:
                return JSONResponse(
                    status_code=403,
                    content={"status": "error", "message": "Вы не зарегистрированы в боте. Нажмите /start в боте."},
                )

            # Use widget photo_url if available, otherwise fetch from API
            avatar_url = data.photo_url
            if not avatar_url:
                avatar_url = await get_telegram_avatar_url(tg_id, BOT_TOKEN)

            if avatar_url:
                user.avatar_url = avatar_url
                await session.commit()

        request.session["user_id"] = tg_id
        return {"status": "ok", "message": "Logged in"}

    except ValueError as ve:
        return JSONResponse(status_code=403, content={"status": "error", "message": f"Auth failed: {str(ve)}"})
    except Exception as e:
        logging.error(f"Widget login error: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": "Internal error"})


@router.post("/api/logout")
async def logout(request: Request):
    request.session.pop("user_id", None)
    return {"status": "ok", "message": "Logged out"}



@router.get("/logout")
@router.get("/api/logout")  # Alias for easier frontend access if needed
async def logout_get(request: Request):
    request.session.pop("user_id", None)
    return RedirectResponse(url="/")
