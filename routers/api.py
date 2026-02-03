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

@router.post("/api/get_player")
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
        role_id = data.get('role_id')
        if not role_id: return {"status": "error", "message": "role_id required"}

        async with aiosqlite.connect(DB_NAME) as conn:
            # 1. Fetch Player & User Info
            async with conn.execute("""
                SELECT p.nickname, p.class_id, p.in_clan, p.user_id, p.is_alt,
                       u.telegram_id, u.username, u.afk_start, u.afk_end
                FROM players p
                LEFT JOIN users u ON p.user_id = u.id
                WHERE p.role_id = ?
            """, (role_id,)) as cursor:
                row = await cursor.fetchone()
                if not row: return {"status": "error", "message": "Player not found"}
                
                (p_nick, p_class, p_in_clan, p_user_id, p_is_alt, 
                 u_tg_id, u_username, u_afk_start, u_afk_end) = row

            # --- AUTO-HEAL: If user_id is missing, check Bot's 'characters' table ---
            if not p_user_id and p_nick:
                async with conn.execute("SELECT user_id FROM characters WHERE nickname = ?", (p_nick,)) as cursor:
                    char_row = await cursor.fetchone()
                    if char_row:
                        found_uid = char_row[0]
                        if found_uid:
                            # Found a link in bot! Auto-update 'players'
                            await conn.execute("UPDATE players SET user_id = ? WHERE role_id = ?", (found_uid, role_id))
                            await conn.commit()
                            p_user_id = found_uid
                            async with conn.execute("SELECT telegram_id, username, afk_start, afk_end FROM users WHERE id = ?", (p_user_id,)) as cursor:
                                u_row = await cursor.fetchone()
                                if u_row:
                                    u_tg_id, u_username, u_afk_start, u_afk_end = u_row

            response_data = {
                "role_id": role_id,
                "nickname": p_nick,
                "class_id": p_class,
                "in_clan": bool(p_in_clan),
                "is_alt": bool(p_is_alt),
                "user": None,
                "other_chars": [],
                "queues": [],
                "afk_history": [],
                "all_queues": [] # Context for dropdown
            }
            
            # Fetch all available queues
            async with conn.execute("SELECT id, name FROM queue_types WHERE is_active = 1 ORDER BY name") as cursor:
                all_qs = await cursor.fetchall()
                response_data["all_queues"] = [{"id": q[0], "name": q[1]} for q in all_qs]

            if p_user_id:
                # User Data
                response_data["user"] = {
                    "id": p_user_id,
                    "telegram_id": u_tg_id,
                    "username": u_username,
                    "afk_start": str(u_afk_start) if u_afk_start else None,
                    "afk_end": str(u_afk_end) if u_afk_end else None,
                    "is_afk": bool(u_afk_start)
                }

                # 2. Fetch Other Characters
                async with conn.execute("SELECT nickname, is_main FROM characters WHERE user_id = ?", (p_user_id,)) as cursor:
                    bot_chars = await cursor.fetchall()
                
                bot_nicks = [c[0] for c in bot_chars]
                if p_nick not in bot_nicks: bot_nicks.append(p_nick)

                if bot_nicks:
                    placeholders = ','.join(['?']*len(bot_nicks))
                    async with conn.execute(f"""
                        SELECT role_id, nickname, class_id, is_alt
                        FROM players 
                        WHERE nickname IN ({placeholders}) AND role_id != ?
                    """, (*bot_nicks, role_id)) as cursor:
                        chars = await cursor.fetchall()
                        for c_rid, c_nick, c_cid, c_is_alt in chars:
                             response_data["other_chars"].append({
                                "role_id": c_rid,
                                "nickname": c_nick,
                                "class_id": c_cid,
                                "is_alt": bool(c_is_alt),
                                "class_icon": CLASSES.get(c_cid, ["", "", ""])[1] if c_cid in CLASSES else "❓"
                            })

                # 3. Active Queues
                async with conn.execute("""
                    SELECT e.id, q.name, e.character_name, e.auto_requeue
                    FROM queue_entries e
                    JOIN queue_types q ON e.queue_type_id = q.id
                    WHERE e.user_id = ?
                """, (p_user_id,)) as cursor:
                    queues = await cursor.fetchall()
                    for q_eid, q_name, q_char_name, q_auto in queues:
                        response_data["queues"].append({
                            "entry_id": q_eid,
                            "queue_name": q_name,
                            "signed_char": q_char_name,
                            "is_auto": bool(q_auto)
                        })

                # 4. AFK History
                async with conn.execute("""
                    SELECT id, start_date, end_date
                    FROM afk_history
                    WHERE user_id = ?
                    ORDER BY start_date DESC LIMIT 5
                """, (p_user_id,)) as cursor:
                    history = await cursor.fetchall()
                    for h_id, h_start, h_end in history:
                        response_data["afk_history"].append({
                            "id": h_id,
                            "start": str(h_start),
                            "end": str(h_end)
                        })

        return {"status": "ok", "player": response_data}

    except Exception as e:
        logging.error(f"Error in get_player: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

# --- Management Endpoints ---

@router.post("/api/afk/add")
async def afk_add(request: Request):
    try:
        data = await request.json()
        user_id = data.get('user_id')
        start = data.get('start')
        end = data.get('end')
        if not user_id or not start or not end: return {"status": "error", "message": "Missing fields"}
        
        async with aiosqlite.connect(DB_NAME) as conn:
             await conn.execute("INSERT INTO afk_history (user_id, start_date, end_date, is_active_record) VALUES (?, ?, ?, 0)",
                              (user_id, start, end))
             await conn.commit()
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)}

@router.post("/api/afk/delete")
async def afk_delete(request: Request):
    try:
        data = await request.json()
        afk_id = data.get('afk_id')
        if not afk_id: return {"status": "error", "message": "Missing afk_id"}
        async with aiosqlite.connect(DB_NAME) as conn:
             await conn.execute("DELETE FROM afk_history WHERE id = ?", (afk_id,))
             await conn.commit()
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)}

@router.post("/api/queue/join")
async def queue_join(request: Request):
    try:
        data = await request.json()
        user_id = data.get('user_id')
        queue_id = data.get('queue_id')
        char_name = data.get('character_name')
        auto_requeue = 1 if data.get('auto_requeue') else 0
        if not user_id or not queue_id: return {"status": "error", "message": "Missing fields"}
        
        async with aiosqlite.connect(DB_NAME) as conn:
            # Check for duplicate entry in same queue
            async with conn.execute("""
                SELECT id FROM queue_entries 
                WHERE user_id = ? AND queue_type_id = ?
            """, (user_id, queue_id)) as cursor:
                existing = await cursor.fetchone()
                if existing:
                    return {"status": "error", "message": "Вы уже записаны в эту очередь"}
            
            # Insert with auto_requeue flag
            await conn.execute("""
                INSERT INTO queue_entries (user_id, queue_type_id, character_name, auto_requeue)
                VALUES (?, ?, ?, ?)
            """, (user_id, queue_id, char_name, auto_requeue))
            await conn.commit()
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)}

@router.post("/api/queue/leave")
async def queue_leave(request: Request):
    try:
        data = await request.json()
        entry_id = data.get('entry_id')
        if not entry_id: return {"status": "error", "message": "Missing entry_id"}
        async with aiosqlite.connect(DB_NAME) as conn:
            await conn.execute("DELETE FROM queue_entries WHERE id = ?", (entry_id,))
            await conn.commit()
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)}

@router.post("/api/character/link")
async def char_link(request: Request):
    try:
        data = await request.json()
        user_id = data.get('user_id')
        nickname = data.get('nickname')
        if not user_id or not nickname: return {"status": "error", "message": "Missing fields"}
        
        async with aiosqlite.connect(DB_NAME) as conn:
            # Upsert into characters
            # Check if exists
            async with conn.execute("SELECT id FROM characters WHERE nickname = ?", (nickname,)) as cursor:
                row = await cursor.fetchone()
            
            if row:
                await conn.execute("UPDATE characters SET user_id = ? WHERE nickname = ?", (user_id, nickname))
            else:
                await conn.execute("INSERT INTO characters (user_id, nickname, is_main) VALUES (?, ?, 0)", (user_id, nickname))
            
            # Sync to players
            await conn.execute("UPDATE players SET user_id = ? WHERE nickname = ?", (user_id, nickname))
            await conn.commit()
            
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)}

@router.post("/api/character/unlink")
async def char_unlink(request: Request):
    try:
        data = await request.json()
        role_id = data.get('role_id') # If unlinking by Role ID via Web
        nickname = data.get('nickname') # If unlinking by Name
        
        async with aiosqlite.connect(DB_NAME) as conn:
            if role_id:
                await conn.execute("UPDATE players SET user_id = NULL WHERE role_id = ?", (role_id,))
                # Also find name to unlink from characters
                async with conn.execute("SELECT nickname FROM players WHERE role_id = ?", (role_id,)) as cursor:
                    r = await cursor.fetchone()
                    if r: nickname = r[0]
            
            if nickname:
                 await conn.execute("DELETE FROM characters WHERE nickname = ?", (nickname,))
                 await conn.execute("UPDATE players SET user_id = NULL WHERE nickname = ?", (nickname,))
            
            await conn.commit()
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)}


# --- КП (Constant Party) Management ---

@router.post("/api/party/get")
async def party_get(request: Request):
    """Get party members for a player."""
    try:
        data = await request.json()
        role_id = data.get('role_id')
        if not role_id: return {"status": "error", "message": "role_id required"}
        
        async with aiosqlite.connect(DB_NAME) as conn:
            # Find party membership for this player
            async with conn.execute("""
                SELECT pm.party_id, pm.is_leader
                FROM party_members pm
                WHERE pm.player_role_id = ?
            """, (role_id,)) as cursor:
                row = await cursor.fetchone()
            
            if not row:
                return {"status": "ok", "party": None, "members": []}
            
            party_id, is_leader = row
            
            # Get party name
            async with conn.execute("SELECT name FROM constant_parties WHERE id = ?", (party_id,)) as cursor:
                party_row = await cursor.fetchone()
                party_name = party_row[0] if party_row and party_row[0] else None
            
            # Get all party members
            members = []
            async with conn.execute("""
                SELECT pm.player_role_id, pm.is_leader, p.nickname, p.class_id
                FROM party_members pm
                LEFT JOIN players p ON pm.player_role_id = p.role_id
                WHERE pm.party_id = ?
                ORDER BY pm.is_leader DESC, p.nickname
            """, (party_id,)) as cursor:
                rows = await cursor.fetchall()
                for m_role_id, m_is_leader, m_nick, m_class_id in rows:
                    members.append({
                        "role_id": m_role_id,
                        "nickname": m_nick or f"ID {m_role_id}",
                        "class_id": m_class_id or -1,
                        "is_leader": bool(m_is_leader)
                    })
            
            return {
                "status": "ok", 
                "party": {"id": party_id, "name": party_name, "is_leader": bool(is_leader)},
                "members": members
            }
    except Exception as e: 
        logging.error(f"Error in party_get: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/api/party/add")
async def party_add(request: Request):
    """Add a player to party. Creates party if needed."""
    try:
        data = await request.json()
        leader_role_id = data.get('leader_role_id')  # Current player (who triggers add)
        member_nickname = data.get('nickname')  # Nickname to add
        
        if not leader_role_id or not member_nickname:
            return {"status": "error", "message": "Missing fields"}
        
        async with aiosqlite.connect(DB_NAME) as conn:
            # Find new member by nickname
            async with conn.execute("SELECT role_id FROM players WHERE nickname = ?", (member_nickname,)) as cursor:
                member_row = await cursor.fetchone()
            
            if not member_row:
                return {"status": "error", "message": f"Игрок '{member_nickname}' не найден"}
            
            member_role_id = member_row[0]
            
            # Check if member already in a party
            async with conn.execute("SELECT party_id FROM party_members WHERE player_role_id = ?", (member_role_id,)) as cursor:
                existing = await cursor.fetchone()
                if existing:
                    return {"status": "error", "message": f"Игрок уже состоит в другой КП"}
            
            # Find or create party for leader
            async with conn.execute("SELECT party_id FROM party_members WHERE player_role_id = ?", (leader_role_id,)) as cursor:
                leader_party = await cursor.fetchone()
            
            if leader_party:
                party_id = leader_party[0]
            else:
                # Create new party with leader
                await conn.execute("INSERT INTO constant_parties (name) VALUES (NULL)")
                async with conn.execute("SELECT last_insert_rowid()") as cursor:
                    party_id = (await cursor.fetchone())[0]
                # Add leader as first member
                await conn.execute(
                    "INSERT INTO party_members (party_id, player_role_id, is_leader) VALUES (?, ?, 1)",
                    (party_id, leader_role_id)
                )
            
            # Add new member
            await conn.execute(
                "INSERT INTO party_members (party_id, player_role_id, is_leader) VALUES (?, ?, 0)",
                (party_id, member_role_id)
            )
            await conn.commit()
            
        return {"status": "ok", "message": f"Игрок {member_nickname} добавлен в КП"}
    except Exception as e: 
        logging.error(f"Error in party_add: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/api/party/remove")
async def party_remove(request: Request):
    """Remove a player from party."""
    try:
        data = await request.json()
        member_role_id = data.get('member_role_id')
        
        if not member_role_id:
            return {"status": "error", "message": "member_role_id required"}
        
        async with aiosqlite.connect(DB_NAME) as conn:
            # Get party id before delete
            async with conn.execute("SELECT party_id FROM party_members WHERE player_role_id = ?", (member_role_id,)) as cursor:
                row = await cursor.fetchone()
            
            if not row:
                return {"status": "error", "message": "Игрок не состоит в КП"}
            
            party_id = row[0]
            
            # Remove member
            await conn.execute("DELETE FROM party_members WHERE player_role_id = ?", (member_role_id,))
            
            # Check if party is empty or has only 1 member left - delete party
            async with conn.execute("SELECT COUNT(*) FROM party_members WHERE party_id = ?", (party_id,)) as cursor:
                count = (await cursor.fetchone())[0]
            
            if count == 0:
                await conn.execute("DELETE FROM constant_parties WHERE id = ?", (party_id,))
            
            await conn.commit()
            
        return {"status": "ok"}
    except Exception as e: 
        logging.error(f"Error in party_remove: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/api/party/rename")
async def party_rename(request: Request):
    """Rename a party."""
    try:
        data = await request.json()
        party_id = data.get('party_id')
        new_name = data.get('name', '').strip() or None  # Empty string = None
        
        if not party_id:
            return {"status": "error", "message": "party_id required"}
        
        async with aiosqlite.connect(DB_NAME) as conn:
            await conn.execute("UPDATE constant_parties SET name = ? WHERE id = ?", (new_name, party_id))
            await conn.commit()
            
        return {"status": "ok"}
    except Exception as e: 
        logging.error(f"Error in party_rename: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@router.post("/api/update_player")
async def update_player(request: Request):
    """
    Update Player Data + Sync Bot Data (User, Character, AFK)
    """
    try:
        data = await request.json()
        role_id = data.get('role_id')
        nickname = data.get('nickname')
        class_id = data.get('class_id')
        in_clan = data.get('in_clan') 
        
        telegram_id_input = data.get('telegram_id') 
        is_alt = data.get('is_alt')
        
        # AFK Dates (Strings "YYYY-MM-DD" or similar)
        afk_start_str = data.get('afk_start') 
        afk_end_str = data.get('afk_end')

        if not role_id: return {"status": "error", "message": "role_id required"}
        
        logging.info(f"API update_player: {role_id} nick={nickname} tg={telegram_id_input} afk={afk_start_str}-{afk_end_str}")

        async with aiosqlite.connect(DB_NAME) as conn:
            # 1. Current State
            async with conn.execute("SELECT user_id, nickname FROM players WHERE role_id = ?", (role_id,)) as cursor:
                row = await cursor.fetchone()
                if not row: return {"status": "error", "message": "Player not found"}
                current_user_id, current_nickname = row

            new_user_id = current_user_id

            # 2. Handle User Linking
            if telegram_id_input is not None:
                s_tg = str(telegram_id_input).strip()
                if s_tg == "":
                    new_user_id = None
                else:
                    try:
                        tg_id = int(s_tg)
                        async with conn.execute("SELECT id FROM users WHERE telegram_id = ?", (tg_id,)) as cursor:
                            u_row = await cursor.fetchone()
                            if u_row:
                                new_user_id = u_row[0]
                            else:
                                # Create new User placeholder if not exists?
                                # For now, allow valid TG ID to create a stub user if missing?
                                # Better safey: Only link existing.
                                return {"status": "error", "message": f"User with TG ID {tg_id} not found."}
                    except ValueError:
                        return {"status": "error", "message": "Invalid TG ID"}

            # 3. Update Player Table
            updates = []
            params = []
            if nickname is not None:
                updates.append("nickname = ?")
                params.append(nickname.strip() if nickname else None)
            if class_id is not None:
                if class_id not in CLASSES and class_id != -1: return {"status": "error", "message": "Invalid Class"}
                updates.append("class_id = ?")
                params.append(class_id)
            if in_clan is not None:
                updates.append("in_clan = ?")
                params.append(1 if in_clan else 0)
            if is_alt is not None:
                updates.append("is_alt = ?")
                params.append(1 if is_alt else 0)
            
            updates.append("user_id = ?")
            params.append(new_user_id)
            
            if updates:
                sql = f"UPDATE players SET {', '.join(updates)} WHERE role_id = ?"
                params.append(role_id)
                await conn.execute(sql, tuple(params))

            # 4. SYNC TO BOT TABLES ("characters")
            # Logic: If user_id is set, ensure a row exists in 'characters' for this nickname + user_id.
            # If is_alt is True -> is_main=False. If is_alt=False -> is_main=True (and unset others).
            
            target_nick = nickname.strip() if nickname else current_nickname
            
            if new_user_id and target_nick:
                # Check if this character exists in bot table
                async with conn.execute("SELECT id FROM characters WHERE nickname = ?", (target_nick,)) as cursor:
                    char_row = await cursor.fetchone()
                
                is_main_val = 0 if is_alt else 1
                
                if char_row:
                    # Update existing
                    await conn.execute("UPDATE characters SET user_id = ?, is_main = ? WHERE nickname = ?", 
                                     (new_user_id, is_main_val, target_nick))
                else:
                    # Create new
                    await conn.execute("INSERT INTO characters (user_id, nickname, is_main) VALUES (?, ?, ?)", 
                                     (new_user_id, target_nick, is_main_val))
                
                # If set to MAIN, demote others
                if is_main_val:
                    await conn.execute("UPDATE characters SET is_main = 0 WHERE user_id = ? AND nickname != ?", 
                                     (new_user_id, target_nick))

            # 5. Handle AFK Logic
            if new_user_id:
                # If explicit dates provided
                if afk_start_str is not None: # Even if empty string (clear)
                    start_val = None
                    end_val = None
                    
                    if afk_start_str:
                        # Validate/Parse
                        # Expected format: ISO string or YYYY-MM-DD or DD.MM.YYYY
                        # We store as DateTime in DB.
                        try:
                            # Try parsing ISO first (e.g. from input type=date/datetime-local)
                            from dateutil.parser import parse
                            s_dt = parse(afk_start_str)
                            start_val = s_dt.strftime("%Y-%m-%d %H:%M:%S")
                        except: pass
                        
                    if afk_end_str:
                        try:
                            from dateutil.parser import parse
                            e_dt = parse(afk_end_str)
                            end_val = e_dt.strftime("%Y-%m-%d %H:%M:%S")
                        except: pass

                    await conn.execute("UPDATE users SET afk_start = ?, afk_end = ? WHERE id = ?", 
                                     (start_val, end_val, new_user_id))

            await conn.commit()
            return {"status": "ok", "message": "Saved & Synced"}

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
