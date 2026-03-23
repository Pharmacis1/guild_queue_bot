import asyncio
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
import aiohttp
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Web imports
from starlette.middleware.sessions import SessionMiddleware

from database import ScheduledAnnouncement, init_db, AsyncSessionLocal
from handlers import admin, user, ai_admin, ai_user
from handlers.admin import schedule_job

# Bot imports
from loader import bot, dp, scheduler
from routers import admin_browser, api, auth, observer, views, api_dashboard

# --- WEB APP SETUP ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Browser
    # from routers import observer
    # await observer.init_browser()
    yield
    # Shutdown: Close Browser
    # await observer.close_browser()

app = FastAPI(lifespan=lifespan)

# Session Middleware (Needed for Auth)
SECRET_KEY = os.getenv("BOT_TOKEN", "super-secret-key-fallback")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=False)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Include Routers
app.include_router(views.router)
app.include_router(api.router)
app.include_router(auth.router)
app.include_router(admin_browser.router)
app.include_router(observer.router)
app.include_router(api_dashboard.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Global Exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"status": "error", "message": f"Internal Server Error: {str(exc)}"})


async def main():
    # 0. Init Database
    await init_db()
    
    # 1. Init Web DB
    # 1. Web DB init removed (handled by async init_db)
    pass

    # 1.1 Observer Browser Init is handled by FastAPI lifespan

    # 2. Bot Setup - Menu
    from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

    await bot.set_my_commands([BotCommand(command="/start", description="🏠 Главное меню")])
    
    # Set Menu Button (WebApp)
    site_url = os.getenv("SITE_URL")
    if not site_url:
        logging.warning("⚠️ SITE_URL is not set in .env! Menu button might not work.")
    else:
        print(f"DEBUG: Setting menu button to SITE_URL: '{site_url}'")
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="📱 Мой Профиль", web_app=WebAppInfo(url=site_url))
            )
        except Exception as e:
            logging.error(f"Failed to set menu button: {e}")

    # 3. Restore Scheduled Tasks
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(select(ScheduledAnnouncement).filter_by(is_active=True))
        tasks = result.scalars().all()
        count = 0
        for t in tasks:
            if t.schedule_type != "once_now":
                schedule_job(t, bot)
                count += 1

    # 3.1 Schedule Daily Backup (at 04:00 AM)
    from scripts.backup_db import perform_backup

    scheduler.add_job(perform_backup, "cron", hour=4, minute=0, id="daily_backup", replace_existing=True)
    # Also run one immediately on startup if needed, or just rely on schedule.
    # Let's run safe backup on startup to be sure.
    perform_backup("startup_auto")
    print("Backup system initialized.")

    # 3.2 Schedule DB Update Reminders for Masters
    from logic.reminders import send_db_upload_reminder

    # Single daily reminder: 19:30 (check 20 hrs window back to 23:30 yesterday)
    scheduler.add_job(send_db_upload_reminder, "cron", hour=19, minute=30, args=[bot, 20.0], id="db_reminder_1930", replace_existing=True)
    print("DB Reminder system initialized.")

    # 4. Start Scheduler
    scheduler.start()
    print(f"Bot started. Jobs restored: {count}")
    print("Version: 2.5.0 (AI Features + RAG + Summary)")


    # Setup Bot Routers
    from middlewares import DbSessionMiddleware
    dp.update.outer_middleware(DbSessionMiddleware())
    
    dp.include_router(user.router)
    dp.include_router(admin.router)
    dp.include_router(ai_admin.router)
    dp.include_router(ai_user.router)

    await bot.delete_webhook(drop_pending_updates=True)

    # Configure Web Server
    port = int(os.getenv("WEB_PORT", 8081))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)

    # Run Bot and Web Concurrently
    await asyncio.gather(dp.start_polling(bot), server.serve())

# --- FRONTEND PROXY ---
# Proxy static nextjs assets
@app.get("/_next/{full_path:path}")
async def proxy_next_assets(full_path: str):
    frontend_url = os.getenv("FRONTEND_URL", "http://frontend:3000")
    target_url = f"{frontend_url}/_next/{full_path}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(target_url) as resp:
                content = await resp.read()
                return Response(content=content, status_code=resp.status, media_type=resp.headers.get("content-type"))
        except Exception as e:
            return JSONResponse({"status": "error", "message": f"Proxy Error: {str(e)}"}, status_code=502)

# Catch-all for React Routes
@app.get("/{full_path:path}")
async def serve_react_app(full_path: str):
    # Skip API/Static/Admin (handled by other routers)
    if full_path.startswith("api") or full_path.startswith("static") or full_path.startswith("admin"):
         # Let FastAPI handle 404 for these if no router matches
        return JSONResponse({"status": "error", "message": "Not Found"}, status_code=404)

    # Proxy to frontend container
    frontend_url = os.getenv("FRONTEND_URL", "http://frontend:3000")
    target_url = f"{frontend_url}/{full_path}"
    if not full_path:  # Root path
        target_url = f"{frontend_url}/"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(target_url) as resp:
                content = await resp.read()
                return Response(content=content, status_code=resp.status, media_type=resp.headers.get("content-type"))
        except Exception as e:
            # Fallback to index.html for SPA routing (if 404 from frontend asset, it might be a route)
            # But Next.js standalone handles routes. If connection fails:
            return JSONResponse({"status": "error", "message": f"Frontend Unavailable: {str(e)}"}, status_code=502)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped")

