# Try to import dependencies
import logging
import os
import shutil
from datetime import datetime

import aiosqlite
import pytz
from fastapi import APIRouter, BackgroundTasks, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

import web_database
from consts import CLASSES

# Try to import dependencies


try:
    from scripts.item_scraper import run_item_scraper
except ImportError:
    run_item_scraper = None
    logging.warning("Could not import run_item_scraper from scripts.item_scraper")

from logic import log_importer, party_manager, queue_manager
from logic.player_manager import update_player_logic

router = APIRouter(prefix="/api")


@router.get("/download/watcher")
async def download_watcher():
    # Modified to look for file in local dist or current dir or just return error
    zip_path = "dist/PW_Requiem_history.zip"

    # We might not have the dist folder in this extracted version
    if not os.path.exists(zip_path):
        return JSONResponse(status_code=404, content={"error": "Download file not found on this server."})

    return FileResponse(path=zip_path, filename="PW_Requiem_history.zip", media_type="application/zip")


@router.post("/upload")
async def upload_log(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """API endpoint to upload logs via utility"""
    temp_path = f"temp_upload_{file.filename}"

    try:
        # 1. Save file
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 2. Process via Logic Layer
        result, missing_item_ids, should_run_pwobs = await log_importer.process_log_upload(temp_path)

        if result.get("status") == "error":
            return result

        # 3. Handle Background Actions

        # Trigger Item Scraper
        if run_item_scraper and missing_item_ids:
            logging.info(f"Triggering background item scraper for {len(missing_item_ids)} items")
            background_tasks.add_task(run_item_scraper, list(missing_item_ids))

        # Trigger PWOBS Scraper (if enabled/available)
        if pwobs_scraper and should_run_pwobs:
            background_tasks.add_task(bg_run_scraper, server="capella", only_unknown=True)

        return result

    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/get_player")
async def get_player(request: Request):
    """
    Get detailed player info including:
    - Base Player data
    - Linked User data (Telegram, AFK dates)
    - AFK History (last 5 records)
    - Linked Characters (from Bot's Character table)
    - Active Queues
    - Available Queue Types (for dropdown)
    """
    try:
        data = await request.json()
        role_id = data.get("role_id")

        if not role_id:
            return {"status": "error", "message": "role_id is required"}

        # Use shared logic from player_manager
        response_data = await get_player_profile(role_id)
        
        if not response_data:
             return {"status": "error", "message": "Player not found"}

        # Add "all_queues" for the dropdown (context)
        # We can keep this local or move to manager too, but keeping here is fine for now
        # (Refactoring complete: Logic moved to player_manager)

        return {"status": "ok", "player": response_data}

    except Exception as e:
        logging.error(f"Error in get_player: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# --- Management Endpoints ---


@router.post("/afk/add")
async def afk_add(request: Request):
    try:
        data = await request.json()
        user_id = data.get("user_id")
        role_id = data.get("role_id")
        start = data.get("start")
        end = data.get("end")
        reason = data.get("reason", "").strip() or None

        if (not user_id and not role_id) or not start or not end:
            return {"status": "error", "message": "Missing fields (user_id OR role_id required)"}

        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            await conn.execute(
                "INSERT INTO afk_history (user_id, role_id, start_date, end_date, reason, is_active_record) VALUES (?, ?, ?, ?, ?, 0)",
                (user_id, role_id, start, end, reason),
            )
            await conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}



@router.post("/afk/delete")
async def afk_delete(request: Request):
    try:
        data = await request.json()
        afk_id = data.get("afk_id")
        logging.info(f"API afk_delete: afk_id={afk_id}")
        if not afk_id:
            return {"status": "error", "message": "Missing afk_id"}
        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            await conn.execute("DELETE FROM afk_history WHERE id = ?", (afk_id,))
            await conn.commit()
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Error in afk_delete: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/queue/join")
async def queue_join(request: Request):
    try:
        data = await request.json()
        user_id = data.get("user_id")
        queue_id = data.get("queue_id")
        char_name = data.get("character_name")
        auto_requeue = 1 if data.get("auto_requeue") else 0
        if not user_id or not queue_id:
            return {"status": "error", "message": "Missing fields"}

        return await queue_manager.join_queue(user_id, queue_id, char_name, auto_requeue)
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/queue/leave")
async def queue_leave(request: Request):
    try:
        data = await request.json()
        entry_id = data.get("entry_id")
        if not entry_id:
            return {"status": "error", "message": "Missing entry_id"}
        return await queue_manager.leave_queue(entry_id)
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/character/link")
async def char_link(request: Request):
    try:
        data = await request.json()
        user_id = data.get("user_id")
        nickname = data.get("nickname", "").strip()
        if not user_id or not nickname:
            return {"status": "error", "message": "Missing fields"}

        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            # Upsert into characters
            # Check if exists (case-insensitive)
            async with conn.execute("SELECT id, nickname FROM characters WHERE LOWER(TRIM(nickname)) = LOWER(TRIM(?))", (nickname,)) as cursor:
                row = await cursor.fetchone()

            if row:
                char_id, db_nick = row
                await conn.execute("UPDATE characters SET user_id = ? WHERE id = ?", (user_id, char_id))
                target_nick = db_nick # Use case from DB
            else:
                await conn.execute(
                    "INSERT INTO characters (user_id, nickname, is_main) VALUES (?, ?, 0)", (user_id, nickname)
                )
                target_nick = nickname

            # Sync to players
            await conn.execute("UPDATE players SET user_id = ? WHERE LOWER(TRIM(nickname)) = LOWER(TRIM(?))", (user_id, target_nick))
            await conn.commit()

        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/character/unlink")
async def char_unlink(request: Request):
    try:
        data = await request.json()
        role_id = data.get("role_id")  # If unlinking by Role ID via Web
        nickname = data.get("nickname")  # If unlinking by Name

        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            if role_id:
                await conn.execute("UPDATE players SET user_id = NULL WHERE role_id = ?", (role_id,))
                # Also find name to unlink from characters
                async with conn.execute("SELECT nickname FROM players WHERE role_id = ?", (role_id,)) as cursor:
                    r = await cursor.fetchone()
                    if r:
                        nickname = r[0]

            if nickname:
                nickname = nickname.strip()
                await conn.execute("DELETE FROM characters WHERE LOWER(TRIM(nickname)) = LOWER(TRIM(?))", (nickname,))
                await conn.execute("UPDATE players SET user_id = NULL WHERE LOWER(TRIM(nickname)) = LOWER(TRIM(?))", (nickname,))

            await conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# --- КП (Constant Party) Management ---


@router.post("/party/get")
async def party_get(request: Request):
    """Get party members for a player."""
    try:
        data = await request.json()
        role_id = data.get("role_id")
        if not role_id:
            return {"status": "error", "message": "role_id required"}

        if not role_id:
            return {"status": "error", "message": "role_id required"}

        return await party_manager.get_party(role_id)
    except Exception as e:
        logging.error(f"Error in party_get: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/party/add_member")
async def party_add_member(request: Request):
    """Add a player to an existing party by nickname."""
    try:
        data = await request.json()
        party_id = data.get("party_id")
        member_nickname = data.get("nickname")
        logging.info(f"API party_add_member: party_id={party_id}, nickname={member_nickname}")

        if not party_id or not member_nickname:
            return {"status": "error", "message": "Missing fields"}

        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            # Find new member by nickname
            async with conn.execute("SELECT role_id FROM players WHERE nickname = ?", (member_nickname,)) as cursor:
                member_row = await cursor.fetchone()

            if not member_row:
                return {"status": "error", "message": f"Игрок '{member_nickname}' не найден"}

            member_role_id = member_row[0]

            # Check if member already in THIS party (optional, but good to prevent duplicates)
            async with conn.execute(
                "SELECT 1 FROM party_members WHERE party_id = ? AND player_role_id = ?", (party_id, member_role_id)
            ) as cursor:
                if await cursor.fetchone():
                    return {"status": "error", "message": "Игрок уже состоит в этой КП"}
            
            # Removed restriction: "Игрок уже состоит в другой КП" - now allowed.

            # Add to party
            await conn.execute(
                "INSERT INTO party_members (party_id, player_role_id, is_leader) VALUES (?, ?, 0)",
                (party_id, member_role_id),
            )
            await conn.commit()

        return {"status": "ok", "message": f"Игрок {member_nickname} добавлен в КП"}
    except Exception as e:
        logging.error(f"Error in party_add_member: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/party/add")
async def party_add(request: Request):
    """Add a player to party. Creates party if needed."""
    try:
        data = await request.json()
        leader_role_id = data.get("leader_role_id")  # Current player (who triggers add)
        member_nickname = data.get("nickname")  # Nickname to add
        logging.info(f"API party_add: leader_role_id={leader_role_id}, nickname={member_nickname}")

        if not leader_role_id or not member_nickname:
            return {"status": "error", "message": "Missing fields"}

        return await party_manager.add_to_party(leader_role_id, member_nickname)
    except Exception as e:
        logging.error(f"Error in party_add: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}



@router.post("/party/remove")
async def party_remove(request: Request):
    """Remove a player from party."""
    try:
        data = await request.json()
        member_role_id = data.get("member_role_id")

        if not member_role_id:
            return {"status": "error", "message": "member_role_id required"}

        if not member_role_id:
            return {"status": "error", "message": "member_role_id required"}

        return await party_manager.remove_from_party(member_role_id)
    except Exception as e:
        logging.error(f"Error in party_remove: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/party/rename")
async def party_rename(request: Request):
    """Rename a party."""
    try:
        data = await request.json()
        party_id = data.get("party_id")
        new_name = data.get("name", "").strip() or None  # Empty string = None

        if not party_id:
            return {"status": "error", "message": "party_id required"}

        return await party_manager.rename_party(party_id, new_name)
    except Exception as e:
        logging.error(f"Error in party_rename: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/party/color")
async def party_color(request: Request):
    """Update party color."""
    try:
        data = await request.json()
        party_id = data.get("party_id")
        color = data.get("color", "").strip() or None

        if not party_id:
            return {"status": "error", "message": "party_id required"}

        return await party_manager.update_party_color(party_id, color)
    except Exception as e:
        logging.error(f"Error in party_color: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/party/kick")
async def party_kick(request: Request):
    """Remove a player from party (Kick)."""
    try:
        data = await request.json()
        member_role_id = data.get("member_role_id")
        
        if not member_role_id:
            return {"status": "error", "message": "member_role_id required"}

        return await party_manager.remove_from_party(member_role_id)
    except Exception as e:
        logging.error(f"Error in party_kick: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/party/transfer_leadership")
async def party_transfer_leadership(request: Request):
    """Transfer party leadership."""
    try:
        data = await request.json()
        party_id = data.get("party_id")
        new_leader_role_id = data.get("new_leader_role_id")

        if not party_id or not new_leader_role_id:
            return {"status": "error", "message": "Missing fields"}

        return await party_manager.transfer_leadership(party_id, new_leader_role_id)
    except Exception as e:
        logging.error(f"Error in party_transfer_leadership: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}



@router.post("/update_player")
async def update_player(request: Request):
    """
    Update Player Data + Sync Bot Data (User, Character, AFK)
    Refactored to use shared logic.
    """
    try:
        data = await request.json()
        role_id = data.get("role_id")

        if not role_id:
            return {"status": "error", "message": "role_id required"}

        # Delegate to shared logic
        # logic handles DB connection and complex sync
        result = await update_player_logic(role_id, data)
        return result

    except Exception as e:
        logging.error(f"Error in update_player: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/update_nickname")
async def update_nickname(request: Request):
    """API endpoint to update player nickname"""
    try:
        data = await request.json()
        role_id = data.get("role_id")
        nickname = data.get("nickname", "").strip()

        if not role_id:
            return {"status": "error", "message": "role_id is required"}

        async with aiosqlite.connect(web_database.DB_NAME) as conn:
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


@router.post("/update_class")
async def update_class(request: Request):
    """API endpoint to update player class"""
    try:
        data = await request.json()
        role_id = data.get("role_id")
        class_id = data.get("class_id")

        if not role_id:
            return {"status": "error", "message": "role_id is required"}

        if class_id is not None and class_id not in CLASSES and class_id != -1:
            return {"status": "error", "message": f"Invalid class_id: {class_id}"}

        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            async with conn.execute("SELECT 1 FROM players WHERE role_id = ?", (role_id,)) as cursor:
                if not await cursor.fetchone():
                    return {"status": "error", "message": f"Player ID {role_id} not found"}

            await conn.execute("UPDATE players SET class_id = ? WHERE role_id = ?", (class_id, role_id))
            await conn.commit()

        class_name = CLASSES.get(class_id, ("Неизвестно", "", ""))[0] if class_id in CLASSES else "Не указан"
        return {"status": "ok", "message": f"Class updated for ID {role_id} to {class_name}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/update_status")
async def update_status(request: Request):
    """API endpoint to update player in_clan status"""
    try:
        data = await request.json()
        role_id = data.get("role_id")
        in_clan = data.get("in_clan")  # Expects boolean or 0/1

        logging.info(f"API update_status: role_id={role_id}, in_clan={in_clan}")

        if not role_id:
            return {"status": "error", "message": "role_id is required"}

        # Convert to int (0 or 1)
        in_clan_val = 1 if in_clan else 0

        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            async with conn.execute("SELECT 1 FROM players WHERE role_id = ?", (role_id,)) as cursor:
                if not await cursor.fetchone():
                    return {"status": "error", "message": f"Player ID {role_id} not found"}

            await conn.execute("UPDATE players SET in_clan = ? WHERE role_id = ?", (in_clan_val, role_id))
            await conn.commit()

        return {"status": "ok", "message": f"Status updated for ID {role_id} to {in_clan_val}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/update_event_date")
async def update_event_date(request: Request):
    """API endpoint to update event date"""
    try:
        msk_tz = pytz.timezone("Europe/Moscow")

        data = await request.json()
        role_id = data.get("role_id")
        # old_val = data.get("old_val")
        # Events doesn't have a unique ID. Composite key: role_id, timestamp
        # But user sends original string or timestamp?
        # Let's use old_timestamp (int) + role_id to identify.
        old_ts = int(data.get("old_timestamp"))
        new_date_str = data.get("new_date_str")  # "YYYY-MM-DD HH:MM:SS"

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

        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            # We match by role_id and specific timestamp (or approx if needed, but precise is better)
            # Risk: duplicates. But LIMIT 1 helps.
            async with conn.execute(
                "SELECT 1 FROM events WHERE role_id = ? AND timestamp = ?", (role_id, old_ts)
            ) as cursor:
                if not await cursor.fetchone():
                    return {"status": "error", "message": "Event not found"}

            await conn.execute(
                """
                UPDATE events 
                SET timestamp = ?, event_date = ? 
                WHERE role_id = ? AND timestamp = ?
            """,
                (new_ts, new_date_str, role_id, old_ts),
            )
            await conn.commit()

        return {"status": "ok", "message": "Date updated"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# --- SCRAPER INTEGRATION ---


# We do a deferred import or handle check to avoid breaking if not present
try:
    from scripts import pwobs_scraper
except ImportError:
    pwobs_scraper = None
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


@router.post("/scrape_players")
async def trigger_scrape(background_tasks: BackgroundTasks, request: Request):
    if not pwobs_scraper:
        return JSONResponse(status_code=500, content={"status": "error", "message": "Scraper module missing"})

    data = await request.json()
    server = data.get("server", "capella")

    background_tasks.add_task(bg_run_scraper, server)

    return {"status": "ok", "message": f"Scraper started for {server}. This may take a while."}


@router.get("/debug_screenshot")
async def get_debug_screenshot():
    """Returns the login_failed.png if it exists."""
    screenshot_path = "login_failed.png"
    if not os.path.exists(screenshot_path):
        return JSONResponse(status_code=404, content={"error": "No debug screenshot found."})
    return FileResponse(screenshot_path, media_type="image/png")


@router.post("/scan/players")
async def force_player_scan(background_tasks: BackgroundTasks):
    from scripts.pwobs_scraper import run_scraper

    background_tasks.add_task(run_scraper, headless=True, only_unknown=True)
    return {"status": "ok", "message": "Player scan triggered in background"}


@router.post("/add_event")
async def add_event(request: Request):
    """
    API endpoint to manually add an event (Valor)
    """
    try:
        msk_tz = pytz.timezone("Europe/Moscow")

        data = await request.json()
        role_id = data.get("role_id")
        event_date_str = data.get("date")  # "YYYY-MM-DD HH:MM:SS" (MSK)
        value = data.get("value")
        description = data.get("description", "")

        if not role_id or not event_date_str or value is None:
            return {"status": "error", "message": "Missing role_id, date, or value"}

        try:
            val_int = int(value)
        except Exception:
            return {"status": "error", "message": "Value must be an integer"}

        # Parse Date
        # Parse Date
        try:
            # Clean input if T exists (HTML5 datetime-local)
            if "T" in event_date_str:
                event_date_str = event_date_str.replace("T", " ")

            # Ensure seconds exist
            if len(event_date_str) == 16:  # 2023-01-01 12:00
                event_date_str += ":00"

            dt_naive = datetime.strptime(event_date_str, "%Y-%m-%d %H:%M:%S")
            dt_msk = msk_tz.localize(dt_naive)
            timestamp = int(dt_msk.timestamp())
        except Exception as date_e:
            return {"status": "error", "message": f"Invalid date format: {date_e}"}

        logging.info(f"Manual Event Add: {role_id}, val={val_int}, ts={timestamp} ({event_date_str})")

        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            # Check player exists
            async with conn.execute("SELECT 1 FROM players WHERE role_id = ?", (role_id,)) as cursor:
                if not await cursor.fetchone():
                    # Auto-create if not exists? Ideally yes for flexibility, but let's stick to existing
                    return {"status": "error", "message": "Player not found"}

            # Insert Event (Type 1 = Valor)
            await conn.execute(
                """
                INSERT INTO events (role_id, timestamp, event_date, event_type, value, raw_desc)
                VALUES (?, ?, ?, 1, ?, ?)
            """,
                (role_id, timestamp, event_date_str, val_int, description),
            )

            await conn.commit()

        return {"status": "ok", "message": "Event added successfully"}

    except Exception as e:
        logging.error(f"Error in add_event: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/delete_event")
async def delete_event(request: Request):
    """
    API endpoint to delete an event (Admin only ideally, but we check logic in frontend/middleware usually)
    """
    try:
        data = await request.json()
        role_id = data.get("role_id")
        timestamp = data.get("timestamp")

        if not role_id or not timestamp:
            return {"status": "error", "message": "Missing role_id or timestamp"}
        
        logging.info(f"Deleting event: role_id={role_id}, ts={timestamp}")

        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            await conn.execute(
                "DELETE FROM events WHERE role_id = ? AND timestamp = ?",
                (role_id, timestamp)
            )
            await conn.commit()
            
        return {"status": "ok", "message": "Event deleted"}
    except Exception as e:
        logging.error(f"Error in delete_event: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
