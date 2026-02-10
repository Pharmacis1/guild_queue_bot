import asyncio
import logging
import os

import uvicorn
import aiohttp
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Web imports
from starlette.middleware.sessions import SessionMiddleware

from database import ScheduledAnnouncement, init_db, session
from handlers import admin, user, ai_admin, ai_user
from handlers.admin import schedule_job

# Bot imports
from loader import bot, dp, scheduler
from routers import admin_browser, api, auth, observer, views, api_dashboard

# --- WEB APP SETUP ---
app = FastAPI()

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

# --- FRONTEND PROXY ---
# Proxy static nextjs assets
# --- FRONTEND PROXY ---
# Proxy static nextjs assets
@app.get("/_next/{full_path:path}")
async def proxy_next_assets(full_path: str):
    target_url = f"http://frontend:3000/_next/{full_path}"
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
    target_url = f"http://frontend:3000/{full_path}"
    if not full_path:  # Root path
        target_url = "http://frontend:3000/"
    
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
    init_db()  # Init Bot DB (Sync)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped")

