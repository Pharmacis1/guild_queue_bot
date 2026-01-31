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
            
            # Pre-fetch known nicknames for description replacement
            # We collect all IDs mentioned in descriptions or acting
            all_involved_ids = set()
            for row in data:
                all_involved_ids.add(row['role_id'])
                if row['raw_params']:
                    try:
                        p0 = int(row['raw_params'].split(',')[0])
                        all_involved_ids.add(p0)
                    except: pass
            
            # Fetch existing nicknames
            id_to_nick = {}
            if all_involved_ids:
                q_placeholders = ','.join(['?'] * len(all_involved_ids))
                async with conn.execute(f"SELECT role_id, nickname FROM players WHERE role_id IN ({q_placeholders})", list(all_involved_ids)) as fetch_cursor:
                    rows = await fetch_cursor.fetchall()
                    for r_id, r_nick in rows:
                        if r_nick:
                            id_to_nick[r_id] = r_nick

            for row in data:
                rid = row['role_id']
                
                # [FIX] Filter invalid IDs (like ID 1)
                if rid < 16:
                    continue

                etype = row['action_type']
                desc = row['description'] # keep original case for display or lower? user said "ID не заменятеся"
                # Let's keep original string but replace ID if found
                
                val = 0
                target_id = None
                
                if row['raw_params']:
                    try:
                        val = int(row['raw_params'].split(',')[0])
                        target_id = val # p0 is often the target
                        if etype == 0: # Item event
                            item_ids.add(val)
                    except: pass

                # [FIX] Resolve ID in description
                # If description contains "ID 12345", try to replace it
                # The board_parser might produce "Изгнал ID 12345"
                if target_id and f"ID {target_id}" in desc:
                   # Try to find nickname
                   t_nick = id_to_nick.get(target_id)
                   if t_nick:
                       desc = desc.replace(f"ID {target_id}", f"{t_nick}")
                   # else: leave as ID {val}

                # Ensure actor exists
                await cursor.execute("INSERT OR IGNORE INTO players (role_id, in_clan) VALUES (?, 1)", (rid,))
                
                # [FIX] Status Updates
                is_leave_self = (etype == 8) # Покинул гильдию
                is_kick = (etype == 10)      # Изгнал ID ...
                is_join = (etype == 6)       # Вступил (or 1, 2 for contrib means they are in) or "принят" in desc
                
                if is_leave_self:
                    # Actor left
                    await cursor.execute("UPDATE players SET in_clan = 0 WHERE role_id = ?", (rid,))
                
                elif is_kick:
                    # Actor KICKED someone. The TARGET (val) left.
                    # Ensure target exists in DB first (so we can update them)
                    if target_id:
                        await cursor.execute("INSERT OR IGNORE INTO players (role_id, in_clan) VALUES (?, 1)", (target_id,))
                        await cursor.execute("UPDATE players SET in_clan = 0 WHERE role_id = ?", (target_id,))
                        
                elif etype in [1, 2, 6] or "принят" in desc.lower() or "joined" in desc.lower():
                    await cursor.execute("UPDATE players SET in_clan = 1 WHERE role_id = ?", (rid,))
                
                # Event
                await cursor.execute("""
                    INSERT INTO events (role_id, timestamp, event_date, event_type, value, raw_desc)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (rid, row['timestamp'], row['date'], etype, val, desc))
                
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

@router.post("/api/update_player")
async def update_player(request: Request):
    """
    Consolidated endpoint to update all player data (nickname, class, status) in one go.
    """
    try:
        data = await request.json()
        role_id = data.get('role_id')
        nickname = data.get('nickname')
        class_id = data.get('class_id')
        in_clan = data.get('in_clan') # Expects boolean or 0/1

        if not role_id:
            return {"status": "error", "message": "role_id is required"}
        
        logging.info(f"API update_player: role_id={role_id}, nick={nickname}, class={class_id}, in_clan={in_clan}")

        async with aiosqlite.connect(DB_NAME) as conn:
            async with conn.execute("SELECT 1 FROM players WHERE role_id = ?", (role_id,)) as cursor:
                if not await cursor.fetchone():
                    return {"status": "error", "message": f"Player ID {role_id} not found"}
            
            # Build dynamic update query
            updates = []
            params = []
            
            if nickname is not None:
                updates.append("nickname = ?")
                params.append(nickname.strip() if nickname else None)
                
            if class_id is not None:
                # Basic validation
                if class_id not in CLASSES and class_id != -1:
                     return {"status": "error", "message": f"Invalid class_id: {class_id}"}
                updates.append("class_id = ?")
                params.append(class_id)
                
            if in_clan is not None:
                updates.append("in_clan = ?")
                params.append(1 if in_clan else 0)
                
            if updates:
                sql = f"UPDATE players SET {', '.join(updates)} WHERE role_id = ?"
                params.append(role_id)
                await conn.execute(sql, tuple(params))
                await conn.commit()
                return {"status": "ok", "message": f"Updated {len(updates)} fields for player {role_id}"}
            else:
                return {"status": "ok", "message": "No changes requested"}

    except Exception as e:
        logging.error(f"Error in update_player: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

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

@router.post("/api/update_status")
async def update_status(request: Request):
    """API endpoint to update player in_clan status"""
    try:
        data = await request.json()
        role_id = data.get('role_id')
        in_clan = data.get('in_clan') # Expects boolean or 0/1
        
        logging.info(f"API update_status: role_id={role_id}, in_clan={in_clan}")
        
        if not role_id:
            return {"status": "error", "message": "role_id is required"}
        
        # Convert to int (0 or 1)
        in_clan_val = 1 if in_clan else 0
        
        async with aiosqlite.connect(DB_NAME) as conn:
            async with conn.execute("SELECT 1 FROM players WHERE role_id = ?", (role_id,)) as cursor:
                if not await cursor.fetchone():
                    return {"status": "error", "message": f"Player ID {role_id} not found"}
            
            await conn.execute("UPDATE players SET in_clan = ? WHERE role_id = ?", (in_clan_val, role_id))
            await conn.commit()
            
        return {"status": "ok", "message": f"Status updated for ID {role_id} to {in_clan_val}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/api/update_event_date")
async def update_event_date(request: Request):
    """API endpoint to update event date"""
    try:
        from datetime import datetime
        import pytz
        msk_tz = pytz.timezone('Europe/Moscow')
        
        data = await request.json()
        role_id = data.get('role_id')
        old_val = data.get('old_val') # For WHERE clause to find specific event? Or assume one event per second?
        # Events doesn't have a unique ID. Composite key: role_id, timestamp
        # But user sends original string or timestamp?
        # Let's use old_timestamp (int) + role_id to identify.
        old_ts = int(data.get('old_timestamp'))
        new_date_str = data.get('new_date_str') # "YYYY-MM-DD HH:MM:SS"
        
        if not role_id or not old_ts or not new_date_str:
            return {"status": "error", "message": "Missing params"}

        # Calculate new timestamp from string (assuming input is MSK)
        # Parse logic:
        try:
             # Assume input format YYYY-MM-DD HH:MM:SS
             dt_naive = datetime.strptime(new_date_str, "%Y-%m-%d %H:%M:%S")
             dt_msk = msk_tz.localize(dt_naive)
             new_ts = int(dt_msk.timestamp())
        except Exception as date_e:
             return {"status": "error", "message": f"Invalid date format: {date_e}"}
        
        logging.info(f"Updating event: {role_id} from {old_ts} to {new_ts} ({new_date_str})")

        async with aiosqlite.connect(DB_NAME) as conn:
            # We match by role_id and specific timestamp (or approx if needed, but precise is better)
            # Risk: duplicates. But LIMIT 1 helps.
            async with conn.execute("SELECT 1 FROM events WHERE role_id = ? AND timestamp = ?", (role_id, old_ts)) as cursor:
                 if not await cursor.fetchone():
                     return {"status": "error", "message": "Event not found"}
            
            await conn.execute("""
                UPDATE events 
                SET timestamp = ?, event_date = ? 
                WHERE role_id = ? AND timestamp = ?
            """, (new_ts, new_date_str, role_id, old_ts))
            await conn.commit()
            
        return {"status": "ok", "message": "Date updated"}
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



@router.post("/api/scan/players")
async def force_player_scan(background_tasks: BackgroundTasks):
    from scripts.pwobs_scraper import run_scraper
    background_tasks.add_task(run_scraper, headless=True, only_unknown=True)
    return {"status": "ok", "message": "Player scan triggered in background"}


@router.post("/api/add_event")
async def add_event(request: Request):
    """
    API endpoint to manually add an event (Valor)
    """
    try:
        from datetime import datetime
        import pytz
        msk_tz = pytz.timezone('Europe/Moscow')
        
        data = await request.json()
        role_id = data.get('role_id')
        event_date_str = data.get('date') # "YYYY-MM-DD HH:MM:SS" (MSK)
        value = data.get('value')
        description = data.get('description', '')
        
        if not role_id or not event_date_str or value is None:
            return {"status": "error", "message": "Missing role_id, date, or value"}
            
        try:
            val_int = int(value)
        except:
             return {"status": "error", "message": "Value must be an integer"}

        # Parse Date
        # Parse Date
        try:
             # Clean input if T exists (HTML5 datetime-local)
             if 'T' in event_date_str:
                 event_date_str = event_date_str.replace('T', ' ')
             
             # Ensure seconds exist
             if len(event_date_str) == 16: # 2023-01-01 12:00
                 event_date_str += ":00"

             dt_naive = datetime.strptime(event_date_str, "%Y-%m-%d %H:%M:%S")
             dt_msk = msk_tz.localize(dt_naive)
             timestamp = int(dt_msk.timestamp())
        except Exception as date_e:
             return {"status": "error", "message": f"Invalid date format: {date_e}"}
             
        logging.info(f"Manual Event Add: {role_id}, val={val_int}, ts={timestamp} ({event_date_str})")
        
        async with aiosqlite.connect(DB_NAME) as conn:
            # Check player exists
            async with conn.execute("SELECT 1 FROM players WHERE role_id = ?", (role_id,)) as cursor:
                if not await cursor.fetchone():
                     # Auto-create if not exists? Ideally yes for flexibility, but let's stick to existing
                     return {"status": "error", "message": "Player not found"}
            
            # Insert Event (Type 1 = Valor)
            await conn.execute("""
                INSERT INTO events (role_id, timestamp, event_date, event_type, value, raw_desc)
                VALUES (?, ?, ?, 1, ?, ?)
            """, (role_id, timestamp, event_date_str, val_int, description))
            
            await conn.commit()
            
        return {"status": "ok", "message": "Event added successfully"}

    except Exception as e:
        logging.error(f"Error in add_event: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
