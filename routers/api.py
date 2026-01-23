from fastapi import APIRouter, UploadFile, File, Request, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
import shutil
import os
import aiosqlite
from web_database import DB_NAME
from consts import CLASSES

# Try to import dependencies
import logging

# Try to import dependencies
try:
    from scripts.board_parser import parse_board_file
except ImportError:
    logging.warning("Could not import board_parser from scripts.board_parser")
    pass

try:
    from scripts.item_scraper import run_item_scraper
except ImportError:
    run_item_scraper = None
    logging.warning("Could not import run_item_scraper from scripts.item_scraper")

router = APIRouter()

@router.get("/download/watcher")
async def download_watcher():
    # Modified to look for file in local dist or current dir or just return error
    zip_path = "dist/PW_Requiem_history.zip"
    
    # We might not have the dist folder in this extracted version
    if not os.path.exists(zip_path):
        return JSONResponse(status_code=404, content={"error": "Download file not found on this server."})

    return FileResponse(path=zip_path, filename="PW_Requiem_history.zip", media_type='application/zip')

@router.post("/api/upload")
async def upload_log(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """API endpoint to upload logs via utility"""
    temp_path = f"temp_upload_{file.filename}"
    
    try:
        # 1. Save file
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 2. Parse
        data = parse_board_file(temp_path)
        if not data:
            return {"status": "error", "message": "File empty or data too old"}
            
        new_events = 0
        item_ids = set()

        
        # 3. Write to DB
        async with aiosqlite.connect(DB_NAME) as conn:
            cursor = await conn.cursor()
            
            for row in data:
                rid = row['role_id']
                etype = row['action_type']
                desc = row['description'].lower()
                val = 0
                if row['raw_params']:
                    try:
                        val = int(row['raw_params'].split(',')[0])
                        if etype == 0: # Item event
                            item_ids.add(val)
                    except: pass


                # Player
                await cursor.execute("INSERT OR IGNORE INTO players (role_id, in_clan) VALUES (?, 1)", (rid,))
                
                # Status
                is_leave = "покинул" in desc or "изгнан" in desc or "вышел" in desc
                if is_leave:
                    await cursor.execute("UPDATE players SET in_clan = 0 WHERE role_id = ?", (rid,))
                elif etype in [1, 2] or "принят" in desc or "joined" in desc:
                    await cursor.execute("UPDATE players SET in_clan = 1 WHERE role_id = ?", (rid,))
                
                # Event
                await cursor.execute("""
                    INSERT INTO events (role_id, timestamp, event_date, event_type, value, raw_desc)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (rid, row['timestamp'], row['date'], etype, val, row['description']))
                
                if cursor.rowcount > 0:
                    new_events += 1
                    
            await conn.commit()

        # TRIGGER ITEM SCRAPER
        logging.info(f"Checking item scraper trigger: run_item_scraper={run_item_scraper is not None}, item_ids_count={len(item_ids)}")
        if run_item_scraper and item_ids:
            async with aiosqlite.connect(DB_NAME) as conn:
                placeholders = ','.join(['?'] * len(item_ids))
                async with conn.execute(f"SELECT id FROM items WHERE id IN ({placeholders})", list(item_ids)) as cursor:
                    existing_rows = await cursor.fetchall()
                    existing_ids = {r[0] for r in existing_rows}
                
                missing_ids = list(item_ids - existing_ids)
                logging.info(f"Missing item IDs to scrape: {missing_ids}")
                
                if missing_ids:
                    logging.info(f"Triggering background item scraper for {len(missing_ids)} items")
                    background_tasks.add_task(run_item_scraper, missing_ids)
                else:
                    logging.info("No new items to scrape.")
            
        # TRIGGER BACKGROUND SCRAPE (only for unknown players)
        # We assume server name is implicitly Capella or default, as we don't have it in upload args.
        # User requested to run automatically.
        if pwobs_scraper:
            background_tasks.add_task(bg_run_scraper, server="capella", only_unknown=True)
            
        return {"status": "ok", "new_events": new_events, "total_parsed": len(data)}

    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@router.post("/api/update_nickname")
async def update_nickname(request: Request):
    """API endpoint to update player nickname"""
    try:
        data = await request.json()
        role_id = data.get('role_id')
        nickname = data.get('nickname', '').strip()
        
        if not role_id:
            return {"status": "error", "message": "role_id is required"}
        
        async with aiosqlite.connect(DB_NAME) as conn:
            async with conn.execute("SELECT 1 FROM players WHERE role_id = ?", (role_id,)) as cursor:
                if not await cursor.fetchone():
                    return {"status": "error", "message": f"Player ID {role_id} not found"}
            
            if nickname:
                await conn.execute("UPDATE players SET nickname = ? WHERE role_id = ?", (nickname, role_id))
            else:
                await conn.execute("UPDATE players SET nickname = NULL WHERE role_id = ?", (role_id,))
            await conn.commit()
            
        return {"status": "ok", "message": f"Nickname updated for ID {role_id}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/update_class")
async def update_class(request: Request):
    """API endpoint to update player class"""
    try:
        data = await request.json()
        role_id = data.get('role_id')
        class_id = data.get('class_id')
        
        if not role_id:
            return {"status": "error", "message": "role_id is required"}
        
        if class_id is not None and class_id not in CLASSES and class_id != -1:
            return {"status": "error", "message": f"Invalid class_id: {class_id}"}
        
        async with aiosqlite.connect(DB_NAME) as conn:
            async with conn.execute("SELECT 1 FROM players WHERE role_id = ?", (role_id,)) as cursor:
                if not await cursor.fetchone():
                    return {"status": "error", "message": f"Player ID {role_id} not found"}
            
            await conn.execute("UPDATE players SET class_id = ? WHERE role_id = ?", (class_id, role_id))
            await conn.commit()
            
        class_name = CLASSES.get(class_id, ("Неизвестно", "", ""))[0] if class_id in CLASSES else "Не указан"
        return {"status": "ok", "message": f"Class updated for ID {role_id} to {class_name}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- SCRAPER INTEGRATION ---
from fastapi import BackgroundTasks
import asyncio
import logging

# We do a deferred import or handle check to avoid breaking if not present
try:
    from scripts import pwobs_scraper
except ImportError:
    pwobs_scraper = None

SCRAPER_IS_RUNNING = False

async def bg_run_scraper(server: str, only_unknown: bool = False):
    global SCRAPER_IS_RUNNING
    
    if not pwobs_scraper:
        logging.error("Scraper module not found")
        return
        
    if SCRAPER_IS_RUNNING:
        logging.warning("⚠️ Scraper is already running. Skipping duplicate trigger.")
        return

    try:
        SCRAPER_IS_RUNNING = True
        logging.info(f"Triggering background scrape for {server} (only_unknown={only_unknown})")
        stats = await pwobs_scraper.run_scraper(server=server, headless=True, only_unknown=only_unknown)
        logging.info(f"Background scrape finished: {stats}")
    except Exception as e:
        logging.error(f"Background scrape failed: {e}")
    finally:
        SCRAPER_IS_RUNNING = False

@router.post("/api/scrape_players")
async def trigger_scrape(background_tasks: BackgroundTasks, request: Request):
    if not pwobs_scraper:
        return JSONResponse(status_code=500, content={"status": "error", "message": "Scraper module missing"})
    
    data = await request.json()
    server = data.get("server", "capella")
    
    background_tasks.add_task(bg_run_scraper, server)
    
    return {"status": "ok", "message": f"Scraper started for {server}. This may take a while."}

@router.get("/api/debug_screenshot")
async def get_debug_screenshot():
    """Returns the login_failed.png if it exists."""
    screenshot_path = "login_failed.png"
    if not os.path.exists(screenshot_path):
        return JSONResponse(status_code=404, content={"error": "No debug screenshot found."})
    return FileResponse(screenshot_path, media_type="image/png")


