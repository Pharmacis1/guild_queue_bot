import asyncio
import logging
import os
import shutil
from datetime import datetime
import pytz

from fastapi import APIRouter, BackgroundTasks, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from consts import CLASSES

# Try to import dependencies


try:
    from scripts.item_scraper import run_item_scraper
except ImportError:
    run_item_scraper = None
    logging.warning("Could not import run_item_scraper from scripts.item_scraper")

from logic import log_importer, party_manager, queue_manager
from logic.player_manager import update_player_logic, get_player_profile
from logic import reward_ops
from sqlalchemy import func
from database import AsyncSessionLocal, select, delete, update, QueueType, RewardHistory, User, Character, Settings, AFKHistory, get_setting, set_setting, get_msk_now, QueueEntry, Player

router = APIRouter(prefix="/api")


async def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    from sqlalchemy.orm import selectinload
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).options(selectinload(User.characters)).filter_by(telegram_id=user_id)
        )
        return result.scalar_one_or_none()


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
    try:
        data = await request.json()
        role_id = data.get("role_id")
        if not role_id:
            return {"status": "error", "message": "role_id is required"}

        async with AsyncSessionLocal() as session:
            # Use shared logic from player_manager
            response_data = await get_player_profile(session, int(role_id))
            
            if not response_data:
                 return {"status": "error", "message": "Player not found"}

            # Add "queue_types" for the dropdown
            result_qt = await session.execute(select(QueueType).order_by(QueueType.name))
            qt_rows = result_qt.scalars().all()
            response_data["queue_types"] = [{"id": r.id, "name": r.name} for r in qt_rows]

            # Add "verification_code"
            response_data["verification_code"] = await get_setting(session, "verification_code", "")

            return {"status": "ok", "player": response_data}

    except Exception as e:
        logging.error(f"Error in API get_player: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# --- Management Endpoints ---

# --- Master Panel Endpoints ---

@router.get("/master/queues")
async def master_get_queues():
    """Get list of active queues for Master Panel."""
    try:
        async with AsyncSessionLocal() as session:
            result_qt = await session.execute(select(QueueType).filter_by(is_active=True))
            queues = result_qt.scalars().all()
            result = []
            from logic.queue_ops import get_admin_queue_count
            for q in queues:
                count = await get_admin_queue_count(session, q.id)
                result.append({"id": q.id, "name": q.name, "count": count, "is_locked": q.is_locked, "description": q.description})
                
            result_rh = await session.execute(select(func.count(RewardHistory.id)).filter_by(is_notified=False))
            pending_count = result_rh.scalar() or 0
            return {"status": "ok", "queues": result, "pending_notifications": pending_count}
    except Exception as e:
        logging.error(f"Error in master_get_queues: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logging.error(f"Error in master_get_queues: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@router.post("/master/queue_entries")
async def master_get_queue_entries(request: Request):
    """Get list of entries for a specific queue ID."""
    try:
        data = await request.json()
        queue_id = data.get("queue_id")
        if not queue_id:
            return {"status": "error", "message": "queue_id is required"}
            
        from logic.queue_ops import get_admin_queue_entries
        from handlers.admin import get_weekly_valor_map
        from database import get_msk_now, Player
        
        async with AsyncSessionLocal() as session:
            entries = await get_admin_queue_entries(session, queue_id)
            
            nicks = [e.character_name for e in entries]
            valor_map = await get_weekly_valor_map(session, nicks)
            
            # Get class IDs for these nicks
            players_stmt = select(Player).filter(Player.nickname.in_(nicks))
            result_players = await session.execute(players_stmt)
            players = result_players.scalars().all()
            player_map = {p.nickname.lower(): p.class_id for p in players}
            
            now = get_msk_now()
            
            result_entries = []
            for e in entries:
                val = valor_map.get(e.character_name, -1)
                class_id = player_map.get(e.character_name.lower(), -1)
                
                is_afk = False
                # Ensure user is loaded (might need selectinload in get_admin_queue_entries or manual fetch)
                # But get_admin_queue_entries returns scalars, we might need to load user
                from sqlalchemy.orm import selectinload
                # re-fetch entries with user if needed, or get_admin_queue_entries should have selectinload
                # Let's assume e.user is available if get_admin_queue_entries uses selectinload
                
                u = e.user
                if u and u.afk_start and u.afk_end:
                    if u.afk_start <= now <= u.afk_end.replace(hour=23, minute=59, second=59):
                        is_afk = True
                        
                result_entries.append({
                    "id": e.id,
                    "character_name": e.character_name,
                    "valor": val,
                    "is_afk": is_afk,
                    "auto_requeue": e.auto_requeue,
                    "class_id": class_id
                })
                
            return {"status": "ok", "entries": result_entries}
    except Exception as e:
        logging.error(f"Error in master_get_queue_entries: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.get("/master/users")
async def get_master_users(request: Request):
    """List all users for Player Management."""
    try:
        user = await get_current_user(request)
        if not user or not user.is_master:
            return {"status": "error", "message": "Unauthorized"}

        from database import Player
        from sqlalchemy.orm import selectinload
        
        async with AsyncSessionLocal() as session:
            stmt_users = select(User).options(selectinload(User.characters))
            result_users = await session.execute(stmt_users)
            users_list = result_users.scalars().all()

            stmt_players = select(Player)
            result_players = await session.execute(stmt_players)
            players = result_players.scalars().all()
            
            nick_to_role = {p.nickname.lower().strip(): p.role_id for p in players if p.nickname}

            total_users = 0
            active_clan_users = 0
            total_chars = 0
            chars_in_clan = 0
            
            total_clan_players = len([p for p in players if p.in_clan == 1])

            result = []
            for u in users_list:
                is_phantom = u.telegram_id is None or (u.telegram_id > 0 and u.telegram_id < 10000)
                
                main_char = next((c for c in u.characters if c.is_main), None)
                alts = [c.nickname for c in u.characters if not c.is_main]
                
                is_in_clan = False
                char_nicks = [c.nickname.lower().strip() for c in u.characters if c.nickname]
                
                user_players = [p for p in players if p.nickname and p.nickname.lower().strip() in char_nicks]
                
                card_chars_in_clan = 0
                for p in user_players:
                    if p.in_clan == 1:
                        card_chars_in_clan += 1

                if any(p.in_clan == 1 for p in user_players):
                    is_in_clan = True
                
                # Update global stats
                total_users += 1
                if is_in_clan and not is_phantom:
                    active_clan_users += 1

                if not is_phantom:
                    total_chars += len(char_nicks)
                    chars_in_clan += card_chars_in_clan

                # Detailed character info
                all_chars_info = []
                for c in u.characters:
                    char_in_clan = any(p.nickname and p.nickname.lower().strip() == c.nickname.lower().strip() and p.in_clan == 1 for p in players)
                    all_chars_info.append({
                        "nickname": c.nickname,
                        "is_main": c.is_main,
                        "is_in_clan": char_in_clan
                    })

                main_role_id = None
                if main_char:
                    main_role_id = nick_to_role.get(main_char.nickname.lower().strip())

                result.append({
                    "id": u.id,
                    "telegram_id": u.telegram_id,
                    "username": u.username,
                    "main_nickname": main_char.nickname if main_char else None,
                    "main_role_id": main_role_id,
                    "characters": all_chars_info,
                    "is_master": u.is_master,
                    "is_banned": u.is_banned,
                    "is_in_clan": is_in_clan,
                    "is_phantom": is_phantom,
                    "afk_start": u.afk_start.strftime("%Y-%m-%d") if u.afk_start else None,
                    "afk_end": u.afk_end.strftime("%Y-%m-%d") if u.afk_end else None,
                })
        return {
            "status": "ok", 
            "users": result,
            "total_users": total_users,
            "active_clan_users": active_clan_users,
            "total_chars": total_chars,
            "chars_in_clan": chars_in_clan,
            "total_clan_players": total_clan_players
        }
    except Exception as e:
        logging.error(f"Error in get_master_users: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/master/user/toggle_ban")
async def toggle_ban(request: Request):
    """Toggle user ban status."""
    try:
        user = await get_current_user(request)
        if not user or not user.is_master:
            return {"status": "error", "message": "Unauthorized"}

        data = await request.json()
        target_id = data.get("user_id")
        
        async with AsyncSessionLocal() as session:
            target = await session.get(User, target_id)
            if not target:
                return {"status": "error", "message": "User not found"}

            if target.id == user.id:
                return {"status": "error", "message": "Cannot ban yourself"}

            target.is_banned = not target.is_banned
            if target.is_banned:
                # Clear queues
                await session.execute(delete(QueueEntry).where(QueueEntry.user_id == target.id))

            await session.commit()
            return {"status": "ok", "is_banned": target.is_banned}
    except Exception as e:
        logging.error(f"Error in toggle_ban: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/master/user/delete")
async def delete_user(request: Request):
    """Delete a user and all associated data."""
    try:
        user = await get_current_user(request)
        if not user or not user.is_master:
            return {"status": "error", "message": "Unauthorized"}

        data = await request.json()
        target_id = data.get("user_id")
        
        async with AsyncSessionLocal() as session:
            target = await session.get(User, target_id)
            if not target:
                return {"status": "error", "message": "User not found"}

            if target.id == user.id:
                return {"status": "error", "message": "Cannot delete yourself"}

            # Delete associated characters
            await session.execute(delete(Character).where(Character.user_id == target.id))
            # Delete queue entries
            await session.execute(delete(QueueEntry).where(QueueEntry.user_id == target.id))
            # Delete user
            await session.delete(target)
            await session.commit()
            return {"status": "ok"}
    except Exception as e:
        logging.error(f"Error in delete_user: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/master/user/toggle_master")
async def toggle_master(request: Request):
    """Toggle user master status."""
    try:
        user = await get_current_user(request)
        if not user or not user.is_master:
            return {"status": "error", "message": "Unauthorized"}

        data = await request.json()
        target_id = data.get("user_id")
        
        async with AsyncSessionLocal() as session:
            target = await session.get(User, target_id)
            if not target:
                return {"status": "error", "message": "User not found"}

            if target.id == user.id:
                return {"status": "error", "message": "Cannot change your own master status"}

            target.is_master = not target.is_master
            await session.commit()
            return {"status": "ok", "is_master": target.is_master}
    except Exception as e:
        logging.error(f"Error in toggle_master: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.get("/master/settings/verification_code")
async def get_verification_code_endpoint(request: Request):
    """Get current registration verification code."""
    try:
        user = await get_current_user(request)
        if not user or not user.is_master:
            return {"status": "error", "message": "Unauthorized"}

        async with AsyncSessionLocal() as session:
            code = await get_setting(session, "verification_code", "")
            return {"status": "ok", "code": code}
    except Exception as e:
        logging.error(f"Error in get_verification_code: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/master/settings/verification_code")
async def set_verification_code_endpoint(request: Request):
    """Update registration verification code."""
    try:
        user = await get_current_user(request)
        if not user or not user.is_master:
            return {"status": "error", "message": "Unauthorized"}

        data = await request.json()
        code = data.get("code")
        async with AsyncSessionLocal() as session:
            await set_setting(session, "verification_code", code)
            return {"status": "ok"}
    except Exception as e:
        logging.error(f"Error in set_verification_code: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.get("/master/afk")
async def get_master_afk(request: Request):
    """List all currently AFK players."""
    try:
        user = await get_current_user(request)
        if not user or not user.is_master:
            return {"status": "error", "message": "Unauthorized"}

        now = get_msk_now()
        from database import Player
        from sqlalchemy.orm import selectinload
        
        async with AsyncSessionLocal() as session:
            stmt_users = select(User).filter(User.afk_start.isnot(None), User.afk_end.isnot(None)).options(selectinload(User.characters))
            result_users = await session.execute(stmt_users)
            afk_users = result_users.scalars().all()

            stmt_players = select(Player).filter(Player.afk_start.isnot(None), Player.afk_end.isnot(None))
            result_players = await session.execute(stmt_players)
            afk_players = result_players.scalars().all()
            
            result = []
            seen_user_ids = set()

            # Process Users (Linked)
            for u in afk_users:
                s_date = u.afk_start
                e_date = u.afk_end
                
                # In PostgreSQL/SQLAlchemy 2.0 async, these might be datetime or date objects
                if hasattr(s_date, "date"): s_date = s_date.date()
                elif isinstance(s_date, str):
                    try: s_date = datetime.fromisoformat(s_date.replace(" ", "T")).date()
                    except: continue
                    
                if hasattr(e_date, "date"): e_date = e_date.date()
                elif isinstance(e_date, str):
                    try: e_date = datetime.fromisoformat(e_date.replace(" ", "T")).date()
                    except: continue

                # Comparison logic
                if s_date <= now.date() <= e_date:
                    main_char = next((c for c in u.characters if c.is_main), None)
                    result.append({
                        "id": u.id,
                        "nickname": main_char.nickname if main_char else (u.username or f"ID {u.telegram_id}"),
                        "role_id": None,
                        "start": s_date.strftime("%Y-%m-%d") if hasattr(s_date, "strftime") else str(s_date),
                        "end": e_date.strftime("%Y-%m-%d") if hasattr(e_date, "strftime") else str(e_date),
                        "reason": u.afk_reason
                    })
                    seen_user_ids.add(u.id)

            # Process Players (Unlinked or Overlap)
            for p in afk_players:
                if p.user_id and p.user_id in seen_user_ids:
                    continue
                
                s_date = p.afk_start
                e_date = p.afk_end
                # In PostgreSQL/SQLAlchemy 2.0 async, these might be datetime or date objects
                if hasattr(s_date, "date"): s_date = s_date.date()
                elif isinstance(s_date, str):
                    try: s_date = datetime.fromisoformat(s_date.replace(" ", "T")).date()
                    except: continue
                    
                if hasattr(e_date, "date"): e_date = e_date.date()
                elif isinstance(e_date, str):
                    try: e_date = datetime.fromisoformat(e_date.replace(" ", "T")).date()
                    except: continue
                
                if s_date <= now.date() <= e_date:
                    result.append({
                        "id": p.user_id,
                        "nickname": p.nickname,
                        "role_id": p.role_id,
                        "start": s_date.strftime("%Y-%m-%d") if hasattr(s_date, "strftime") else str(s_date),
                        "end": e_date.strftime("%Y-%m-%d") if hasattr(e_date, "strftime") else str(e_date),
                        "reason": p.afk_reason
                    })
            return {"status": "ok", "afk_players": result}
    except Exception as e:
        logging.error(f"Error in get_master_afk: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@router.get("/master/afk/history")
async def get_master_afk_history(request: Request):
    """List all historical AFK records."""
    try:
        user = await get_current_user(request)
        if not user or not user.is_master:
            return {"status": "error", "message": "Unauthorized"}

        from database import AFKHistory, User, Character, Player
        from sqlalchemy.orm import selectinload
        
        async with AsyncSessionLocal() as session:
            # Fetch records joined with user
            stmt = select(AFKHistory).outerjoin(User, AFKHistory.user_id == User.id).options(selectinload(AFKHistory.user).selectinload(User.characters)).order_by(AFKHistory.timestamp.desc())
            result_recs = await session.execute(stmt)
            records = result_recs.scalars().all()
            
            result = []
            for r in records:
                nickname = "Неизвестно"
                s_date = r.start_date
                e_date = r.end_date
                
                if isinstance(s_date, str):
                    try: s_date = datetime.fromisoformat(s_date.replace(" ", "T"))
                    except: pass
                if isinstance(e_date, str):
                    try: e_date = datetime.fromisoformat(e_date.replace(" ", "T"))
                    except: pass

                if r.user:
                    main_char = next((c for c in r.user.characters if c.is_main), None)
                    nickname = main_char.nickname if main_char else (r.user.username or f"ID {r.user.telegram_id}")
                elif hasattr(r, 'role_id') and r.role_id:
                    # Try to get nickname from Player table if User is missing
                    p_stmt = select(Player).filter_by(role_id=r.role_id)
                    p_result = await session.execute(p_stmt)
                    p_row = p_result.scalar_one_or_none()
                    if p_row: nickname = p_row.nickname

                result.append({
                    "id": r.id,
                    "user_id": r.user_id,
                    "nickname": nickname,
                    "start": s_date.strftime("%Y-%m-%d") if hasattr(s_date, 'strftime') else "-",
                    "end": e_date.strftime("%Y-%m-%d") if hasattr(e_date, 'strftime') else "-",
                    "reason": r.reason or "",
                    "timestamp": r.timestamp.strftime("%d.%m %H:%M") if r.timestamp else "-",
                    "is_active_record": r.is_active_record
                })
                
            return {"status": "ok", "history": result}
    except Exception as e:
        logging.error(f"Error in get_master_afk_history: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@router.post("/master/afk/save")
async def save_master_afk(request: Request):
    """Add or update AFK status for a user."""
    try:
        user = await get_current_user(request)
        if not user or not user.is_master:
            return {"status": "error", "message": "Unauthorized"}
        
        data = await request.json()
        target_user_id = data.get("user_id")
        role_id = data.get("role_id")
        start_str = data.get("start")
        end_str = data.get("end")
        reason = data.get("reason", "")
        
        if not (target_user_id or role_id) or not start_str or not end_str:
            return {"status": "error", "message": "Missing required fields"}
            
        from datetime import datetime
        start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
        
        from database import User, Player, AFKHistory, get_msk_now, Character
        
        async with AsyncSessionLocal() as session:
            if target_user_id:
                target_user = await session.get(User, target_user_id)
                if not target_user:
                    return {"status": "error", "message": "User not found"}
                    
                target_user.afk_start = start_date
                target_user.afk_end = end_date
                target_user.afk_reason = reason
                
                # Update characters
                await session.execute(
                    update(Player).filter_by(user_id=target_user_id).values(
                        afk_start=start_date,
                        afk_end=end_date,
                        afk_reason=reason
                    )
                )

                # Main character for history role_id
                if not role_id:
                    stmt_chars = select(Character).filter_by(user_id=target_user_id)
                    res_chars = await session.execute(stmt_chars)
                    user_chars = res_chars.scalars().all()
                    main_char = next((c for c in user_chars if c.is_main), None)
                    if main_char:
                        p_stmt = select(Player).filter_by(nickname=main_char.nickname)
                        p_res = await session.execute(p_stmt)
                        p_row = p_res.scalar_one_or_none()
                        if p_row: role_id = p_row.role_id
            elif role_id:
                player = await session.get(Player, role_id)
                if not player:
                    return {"status": "error", "message": "Player not found"}
                
                player.afk_start = start_date
                player.afk_end = end_date
                player.afk_reason = reason
                
                # If player is linked to user, update user too
                if player.user_id:
                    target_user_id = player.user_id
                    t_user = await session.get(User, target_user_id)
                    if t_user:
                        t_user.afk_start = start_date
                        t_user.afk_end = end_date
                        t_user.afk_reason = reason
            
            # Log to history
            new_hist = AFKHistory(
                user_id=target_user_id,
                role_id=role_id,
                start_date=start_date,
                end_date=end_date,
                reason=reason,
                is_active_record=True,
                timestamp=get_msk_now()
            )
            session.add(new_hist)
            await session.commit()
            
            return {"status": "ok", "message": "AFK статус обновлен"}
    except Exception as e:
        logging.error(f"Error in save_master_afk: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@router.post("/master/afk/delete")
async def delete_master_afk(request: Request):
    """Remove AFK status for a user."""
    try:
        user = await get_current_user(request)
        if not user or not user.is_master:
            return {"status": "error", "message": "Unauthorized"}
            
        data = await request.json()
        target_user_id = data.get("user_id")
        if not target_user_id:
            return {"status": "error", "message": "user_id is required"}
            
        from database import User, Player
        
        async with AsyncSessionLocal() as session:
            target_user = await session.get(User, target_user_id)
            if not target_user:
                return {"status": "error", "message": "User not found"}
                
            target_user.afk_start = None
            target_user.afk_end = None
            target_user.afk_reason = None
            
            # Also clear in players table
            await session.execute(
                update(Player).filter_by(user_id=target_user_id).values(
                    afk_start=None,
                    afk_end=None,
                    afk_reason=None
                )
            )
            await session.commit()
            
            return {"status": "ok", "message": "AFK статус удален"}
    except Exception as e:
        logging.error(f"Error in delete_master_afk: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@router.post("/master/issue_reward")
async def master_issue_reward(request: Request):
    """Issue reward to an entry ID."""
    try:
        data = await request.json()
        entry_id = data.get("entry_id")
        master_id = data.get("master_id") # We need master role id or user id
        
        if not entry_id or not master_id:
            return {"status": "error", "message": "Missing entry_id or master_id"}
            
        async with AsyncSessionLocal() as session:
            # Get master user info
            # 1. Try master_id as user.id
            master = await session.get(User, master_id)
            if not master or not master.is_master:
                # 2. Try master_id as role_id from players table
                p_stmt = select(Player).filter_by(role_id=master_id)
                p_res = await session.execute(p_stmt)
                m_row = p_res.scalar_one_or_none()
                if m_row and m_row.user_id:
                    master = await session.get(User, m_row.user_id)
            
            if not master or not master.is_master:
                return {"status": "error", "message": "Unauthorized or not found."}
                
            # To call issue_reward, we need original QueueEntry details before it's deleted
            from sqlalchemy.orm import selectinload
            stmt_entry = select(QueueEntry).filter_by(id=entry_id).options(
                selectinload(QueueEntry.queue),
                selectinload(QueueEntry.user).selectinload(User.characters)
            )
            res_entry = await session.execute(stmt_entry)
            entry = res_entry.scalar_one_or_none()
            
            if not entry:
                return {"status": "error", "message": "Уже выдано/удалено."}
                
            q_name = entry.queue.name
            char_nick = entry.character_name
            
            main_nick = char_nick
            if entry.user:
                main_char = next((c for c in entry.user.characters if c.is_main), None)
                if main_char:
                    main_nick = main_char.nickname
                    
            success, msg, hist = await reward_ops.issue_reward(session, entry_id, master.username)
            
            if success:
                from utils import check_google_sheet, log_reward_to_sheet
                asyncio.create_task(log_reward_to_sheet(q_name, main_nick, char_nick, master.username))
                return {"status": "ok", "message": msg}
            else:
                return {"status": "error", "message": msg}
    except Exception as e:
        logging.error(f"Error in master_issue_reward: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@router.post("/master/warn_user")
async def master_warn_user(request: Request):
    """Issue warning for an entry ID."""
    try:
        data = await request.json()
        entry_id = data.get("entry_id")
        master_id = data.get("master_id")
        
        if not entry_id or not master_id:
            return {"status": "error", "message": "Missing entry_id or master_id"}
            
        async with AsyncSessionLocal() as session:
            master = await session.get(User, master_id)
            if not master or not master.is_master:
                # Fallback handled similarly to issue_reward
                p_stmt = select(Player).filter_by(role_id=master_id)
                p_res = await session.execute(p_stmt)
                m_row = p_res.scalar_one_or_none()
                if m_row and m_row.user_id:
                    master = await session.get(User, m_row.user_id)
                    
            if not master or not master.is_master:
                return {"status": "error", "message": "Unauthorized or not found."}
                
            success, msg, hist = await reward_ops.warn_user(session, entry_id, master.username)
            return {"status": "ok" if success else "error", "message": msg}
    except Exception as e:
        logging.error(f"Error in master_warn_user: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@router.post("/master/send_notifications")
async def master_send_notifications(request: Request):
    """Send batched reward notifications via telegram."""
    try:
        from loader import bot
        from aiogram import types
        from database import RewardHistory, User
        
        async with AsyncSessionLocal() as session:
            stmt = select(RewardHistory).filter_by(is_notified=False)
            res = await session.execute(stmt)
            pending = res.scalars().all()
            
            if not pending:
                return {"status": "error", "message": "Нет уведомлений для отправки."}
                
            user_map = {}
            for item in pending:
                if item.user_id not in user_map:
                    user_map[item.user_id] = []
                user_map[item.user_id].append(item)
                
            count_users = 0
            for uid, items in user_map.items():
                user = await session.get(User, uid)
                if not user:
                    for i in items:
                        i.is_notified = True
                    continue
                    
                rewards = [i for i in items if i.record_type != "warning"]
                warnings = [i for i in items if i.record_type == "warning"]
                
                msg_text = ""
                if rewards:
                    msg_text += "🎉 <b>Вам выданы награды!</b>\n\n"
                    for item in rewards:
                        msg_text += f"🔹 <b>{item.queue_name}</b> ({item.character_name})\n"
                        item.is_notified = True
                    msg_text += "\n⚠️ <i>Заберите награды из Клан листа в ближайшее время, пока не пропали.</i>\n\n"
                    
                if warnings:
                    if rewards:
                        msg_text += "───────────────\n\n"
                    msg_text += "⚠️ <b>Важные уведомления:</b>\n\n"
                    for item in warnings:
                        msg_text += f"🔸 <b>{item.queue_name}</b> ({item.character_name}):\n<i>Условия очереди не выполнены, награда не выдана.</i>\n\n"
                        item.is_notified = True
                        
                msg_text += "👇 <b>Выберите действие:</b>"
                kb_notify = types.InlineKeyboardMarkup(inline_keyboard=[[
                            types.InlineKeyboardButton(text="📋 Перейти к очередям", callback_data="menu_join"),
                            types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_main"),
                ]])
                
                try:
                    await bot.send_message(user.telegram_id, msg_text, parse_mode="HTML", reply_markup=kb_notify)
                    count_users += 1
                except Exception:
                    pass
                    
            await session.commit()
            return {"status": "ok", "message": f"Уведомления отправлены ({count_users} игр.)"}
    except Exception as e:
        logging.error(f"Error sending notifications: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/master/reorder_queue")
async def master_reorder_queue(request: Request):
    """Update order of entries in a queue."""
    try:
        data = await request.json()
        entry_ids = data.get("entry_ids", [])
        if not entry_ids:
             return {"status": "error", "message": "No entries provided"}
        
        from database import QueueEntry
        async with AsyncSessionLocal() as session:
            for idx, eid in enumerate(entry_ids):
                entry = await session.get(QueueEntry, eid)
                if entry:
                    entry.position = idx
            await session.commit()
            return {"status": "ok", "message": "Порядок обновлен"}
    except Exception as e:
        logging.error(f"Error in reorder_queue: {e}")
        return {"status": "error", "message": str(e)}

@router.post("/master/remove_from_queue")
async def master_remove_from_queue(request: Request):
    """Remove a specific entry ID from queue."""
    try:
        data = await request.json()
        entry_id = data.get("entry_id")
        if not entry_id:
            return {"status": "error", "message": "entry_id is required"}
            
        from database import QueueEntry
        async with AsyncSessionLocal() as session:
            entry = await session.get(QueueEntry, entry_id)
            if entry:
                await session.delete(entry)
                await session.commit()
                return {"status": "ok", "message": "Игрок удален из очереди"}
            return {"status": "error", "message": "Запись не найдена"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/master/search_players")
async def master_search_players(request: Request):
    """Search for players by nickname and optional class_id."""
    try:
        data = await request.json()
        query_text = data.get("query", "").strip()
        class_id = data.get("class_id")
        
        from database import Player
        
        async with AsyncSessionLocal() as session:
            stmt = select(Player)
            
            if class_id is not None and class_id != -1:
                stmt = stmt.filter(Player.class_id == class_id)
                
            if query_text:
                # Use ILIKE for Postgres
                stmt = stmt.filter(Player.nickname.ilike(f"%{query_text}%"))
                
            result_proxy = await session.execute(stmt)
            players = result_proxy.scalars().all()
            
            result = []
            for p in players:
                result.append({
                    "nickname": p.nickname or "",
                    "class_id": p.class_id,
                    "has_telegram": p.user_id is not None,
                    "user_id": p.user_id,
                    "role_id": p.role_id
                })
            
            result.sort(key=lambda x: x["nickname"])
            return {"status": "ok", "players": result[:50]}
    except Exception as e:
        logging.error(f"Error in master_search_players: {e}")
        return {"status": "error", "message": str(e)}

@router.post("/master/add_to_queue")
async def master_add_to_queue(request: Request):
    """Manually add a player to a queue."""
    try:
        data = await request.json()
        queue_id = data.get("queue_id")
        char_name = data.get("character_name")
        auto_requeue = data.get("auto_requeue", False)
        
        if not queue_id or not char_name:
            return {"status": "error", "message": "queue_id and character_name are required"}
            
        from database import Player, User, Character, QueueEntry, QueueType
        from sqlalchemy import func
        
        async with AsyncSessionLocal() as session:
            # 1. Try exact match
            stmt = select(Player).filter(Player.nickname == char_name)
            result = await session.execute(stmt)
            player = result.scalar_one_or_none()
            
            if not player:
                # 2. Try case-insensitive fallback
                stmt = select(Player).filter(Player.nickname.ilike(char_name))
                result = await session.execute(stmt)
                player = result.scalar_one_or_none()
                if player: char_name = player.nickname
            
            user_id = player.user_id if player else None
            if not user_id:
                stmt = select(Character).filter(Character.nickname.ilike(char_name))
                result = await session.execute(stmt)
                char = result.scalar_one_or_none()
                if char:
                    user_id = char.user_id
                    char_name = char.nickname
                else:
                    return {"status": "error", "message": f"Игрок '{char_name}' не найден"}
            
            # Already in queue check
            if user_id:
                stmt = select(QueueEntry).filter_by(queue_type_id=queue_id, user_id=user_id)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing: return {"status": "error", "message": "Уже в очереди"}
            
            max_pos_stmt = select(func.max(QueueEntry.position)).filter_by(queue_type_id=queue_id)
            max_pos_res = await session.execute(max_pos_stmt)
            max_pos = max_pos_res.scalar() or 0

            new_entry = QueueEntry(queue_type_id=queue_id, user_id=user_id, character_name=char_name, position=max_pos + 1, auto_requeue=auto_requeue)
            session.add(new_entry)
            await session.commit()
            return {"status": "ok", "message": f"Игрок {char_name} добавлен"}
    except Exception as e:
        logging.error(f"Error in master_add_to_queue: {e}")
        return {"status": "error", "message": str(e)}
@router.post("/master/toggle_auto_requeue")
async def toggle_auto_requeue(request: Request):
    """Toggle auto_requeue flag for a queue entry."""
    try:
        data = await request.json()
        entry_id = data.get("entry_id")
        
        if not entry_id:
            return {"status": "error", "message": "entry_id is required"}
            
        from database import QueueEntry
        async with AsyncSessionLocal() as session:
            entry = await session.get(QueueEntry, entry_id)
            if not entry:
                return {"status": "error", "message": "Запись не найдена"}
                
            entry.auto_requeue = not entry.auto_requeue
            await session.commit()
            
            return {"status": "ok", "auto_requeue": entry.auto_requeue}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/master/settings")
async def master_get_settings():
    """Get global master settings."""
    try:
        from database import get_setting
        async with AsyncSessionLocal() as session:
            default_limit = await get_setting(session, "default_limit", "1")
            return {"status": "ok", "settings": {"default_limit": default_limit}}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/master/settings")
async def master_update_settings(request: Request):
    """Update global master settings."""
    try:
        data = await request.json()
        default_limit = data.get("default_limit")
        if default_limit is not None:
            from database import set_setting
            async with AsyncSessionLocal() as session:
                await set_setting(session, "default_limit", str(default_limit))
                return {"status": "ok", "message": "Настройки обновлены"}
        return {"status": "error", "message": "No settings to update"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/master/user_limit")
async def master_update_user_limit(request: Request):
    """Set personal limit for a user (via user_id or role_id)."""
    try:
        data = await request.json()
        target_user_id = data.get("user_id")
        role_id = data.get("role_id")
        limit = data.get("limit")  # Can be None to clear

        if target_user_id is None and role_id is None:
            return {"status": "error", "message": "user_id or role_id is required"}

        from database import Player, User, Character

        async with AsyncSessionLocal() as session:
            user_obj = None
            if target_user_id is not None:
                user_obj = await session.get(User, target_user_id)
            
            if not user_obj and role_id is not None:
                # Check if this player is already linked to a user
                player = await session.get(Player, role_id)
                if player and player.user_id:
                    user_obj = await session.get(User, player.user_id)
                elif player:
                    # Create a shadow user
                    user_obj = User(username=player.nickname, is_master=False)
                    session.add(user_obj)
                    await session.flush() 
                    player.user_id = user_obj.id
                    
            if not user_obj:
                return {"status": "error", "message": "Пользователь не найден"}

            user_obj.personal_limit = limit
            await session.commit()
            return {"status": "ok", "message": "Лимит обновлен"}
    except Exception as e:
        logging.error(f"Error in master_update_user_limit: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/master/user_limits")
async def master_get_user_limits():
    """Get list of users who have a personal limit set."""
    try:
        from database import User, Player, Character
        from sqlalchemy.orm import selectinload
        
        async with AsyncSessionLocal() as session:
            stmt = select(User).filter(User.personal_limit.isnot(None)).options(selectinload(User.characters))
            res = await session.execute(stmt)
            users = res.scalars().all()
            
            result = []
            for u in users:
                # Try to find a nickname from players table preferentially
                p_stmt = select(Player).filter_by(user_id=u.id)
                p_res = await session.execute(p_stmt)
                player = p_res.scalar_one_or_none()
                
                char_name = player.nickname if player else u.username
                
                # Fallback to characters table
                if not player:
                    main_char = next((c for c in u.characters if c.is_main), None)
                    if main_char:
                        char_name = main_char.nickname
                    elif u.characters:
                        char_name = u.characters[0].nickname
                    
                result.append({
                    "id": u.id,
                    "username": u.username,
                    "display_name": char_name,
                    "personal_limit": u.personal_limit
                })
            return {"status": "ok", "users": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/master/queue_description")
async def master_update_queue_description(request: Request):
    """Update queue description (conditions)."""
    try:
        data = await request.json()
        queue_id = data.get("queue_id")
        description = data.get("description")

        if not queue_id:
            return {"status": "error", "message": "queue_id is required"}

        async with AsyncSessionLocal() as session:
            queue = await session.get(QueueType, queue_id)
            if not queue:
                return {"status": "error", "message": "Очередь не найдена"}

            queue.description = description
            await session.commit()
            return {"status": "ok", "message": "Описание обновлено"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/master/queue_lock")
async def master_toggle_queue_lock(request: Request):
    """Toggle queue lock status."""
    try:
        data = await request.json()
        queue_id = data.get("queue_id")
        is_locked = data.get("is_locked")

        if not queue_id:
            return {"status": "error", "message": "queue_id is required"}

        async with AsyncSessionLocal() as session:
            queue = await session.get(QueueType, queue_id)
            if not queue:
                return {"status": "error", "message": "Очередь не найдена"}

            queue.is_locked = bool(is_locked)
            await session.commit()
            return {"status": "ok", "message": "Статус блокировки изменен"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/master/reward_history")
async def master_get_reward_history(
    queue_name: str = None, 
    character_name: str = None, 
    issued_by: str = None, 
    limit: int = 100, 
    offset: int = 0
):
    """Get reward history with filters."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(RewardHistory)
            if queue_name:
                stmt = stmt.filter(RewardHistory.queue_name.ilike(f"%{queue_name}%"))
            if character_name:
                stmt = stmt.filter(RewardHistory.character_name.ilike(f"%{character_name}%"))
            if issued_by:
                stmt = stmt.filter(RewardHistory.issued_by.ilike(f"%{issued_by}%"))
                
            # Count total
            from sqlalchemy import func
            count_stmt = select(func.count()).select_from(stmt.subquery())
            count_res = await session.execute(count_stmt)
            total = count_res.scalar_one()
            
            # Fetch records
            stmt = stmt.order_by(RewardHistory.timestamp.desc()).limit(limit).offset(offset)
            res = await session.execute(stmt)
            records = res.scalars().all()
            
            result = []
            for r in records:
                result.append({
                    "id": r.id,
                    "user_id": r.user_id,
                    "character_name": r.character_name,
                    "queue_name": r.queue_name,
                    "issued_by": r.issued_by,
                    "is_notified": r.is_notified,
                    "record_type": r.record_type,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None
                })
                
            return {"status": "ok", "history": result, "total": total}
    except Exception as e:
        logging.error(f"Error in master_get_reward_history: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.get("/master/history_suggestions")
async def master_history_suggestions():
    """Get unique values from History for autocomplete."""
    try:
        async with AsyncSessionLocal() as session:
            q_stmt = select(RewardHistory.queue_name).distinct()
            c_stmt = select(RewardHistory.character_name).distinct()
            m_stmt = select(RewardHistory.issued_by).distinct()
            
            queues = (await session.execute(q_stmt)).scalars().all()
            characters = (await session.execute(c_stmt)).scalars().all()
            masters = (await session.execute(m_stmt)).scalars().all()
            
            return {
                "status": "ok",
                "queues": sorted([q for q in queues if q]),
                "characters": sorted([c for c in characters if c]),
                "masters": sorted([m for m in masters if m])
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.delete("/master/reward_history/{record_id}")
async def master_delete_reward_history(record_id: int):
    """Delete a specific reward history record."""
    try:
        async with AsyncSessionLocal() as session:
            record = await session.get(RewardHistory, record_id)
            if not record:
                return {"status": "error", "message": "Запись не найдена"}
                
            await session.delete(record)
            await session.commit()
            return {"status": "ok", "message": "Запись удалена"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/afk/add")
async def afk_add(request: Request):
    try:
        data = await request.json()
        target_user_id = data.get("user_id")
        role_id = data.get("role_id")
        start = data.get("start")
        end = data.get("end")
        reason = data.get("reason", "").strip() or None

        if (not target_user_id and not role_id) or not start or not end:
            return {"status": "error", "message": "Missing fields (user_id OR role_id required)"}

        from database import AFKHistory
        async with AsyncSessionLocal() as session:
            new_afk = AFKHistory(
                user_id=target_user_id,
                role_id=role_id,
                start_date=datetime.strptime(start, "%Y-%m-%d") if isinstance(start, str) else start,
                end_date=datetime.strptime(end, "%Y-%m-%d") if isinstance(end, str) else end,
                reason=reason,
                is_active_record=False
            )
            session.add(new_afk)
            await session.commit()
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Error in afk_add: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}



@router.post("/afk/delete")
async def afk_delete(request: Request):
    try:
        data = await request.json()
        afk_id = data.get("afk_id")
        logging.info(f"API afk_delete: afk_id={afk_id}")
        if not afk_id:
            return {"status": "error", "message": "Missing afk_id"}
            
        from database import AFKHistory, User, Player, update
        async with AsyncSessionLocal() as session:
            afk = await session.get(AFKHistory, afk_id)
            if afk:
                user_id = afk.user_id
                role_id = afk.role_id
                start_date = afk.start_date
                end_date = afk.end_date
                
                # If this record is currently active (matches stored fields), clear them
                if user_id:
                    user = await session.get(User, user_id)
                    if user and user.afk_start == start_date and user.afk_end == end_date:
                        user.afk_start = None
                        user.afk_end = None
                        user.afk_reason = None
                        # Sync all characters of this user
                        await session.execute(
                            update(Player).where(Player.user_id == user_id).values(
                                afk_start=None, afk_end=None, afk_reason=None
                            )
                        )
                elif role_id:
                    player = await session.get(Player, role_id)
                    if player and player.afk_start == start_date and player.afk_end == end_date:
                        player.afk_start = None
                        player.afk_end = None
                        player.afk_reason = None

                await session.delete(afk)
                await session.commit()
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


@router.post("/queue/update_entry")
async def queue_update_entry(request: Request):
    try:
        data = await request.json()
        entry_id = data.get("entry_id")
        character_name = data.get("character_name")
        auto_requeue = 1 if data.get("auto_requeue") else 0
        if not entry_id or not character_name:
            return {"status": "error", "message": "Missing entry_id or character_name"}
        
        from database import QueueEntry
        from sqlalchemy import update
        async with AsyncSessionLocal() as session:
            stmt = update(QueueEntry).where(QueueEntry.id == entry_id).values(
                character_name=character_name,
                auto_requeue=bool(auto_requeue)
            )
            await session.execute(stmt)
            await session.commit()
            
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/character/link")
async def char_link(request: Request):
    try:
        data = await request.json()
        target_user_id = data.get("user_id")
        nickname = data.get("nickname", "").strip()
        if not target_user_id or not nickname:
            return {"status": "error", "message": "Missing fields"}

        async with AsyncSessionLocal() as session:
            # 1. Check if nickname exists in Character table (already linked)
            stmt = select(Character).filter(func.lower(func.trim(Character.nickname)) == func.lower(func.trim(nickname)))
            result = await session.execute(stmt)
            char = result.scalar_one_or_none()

            if char and char.user_id and char.user_id != target_user_id:
                return {"status": "error", "message": "Персонаж уже привязан к другому профилю"}

            # 2. Check if nickname exists in Player table (known char)
            stmt_p = select(Player).filter(func.lower(func.trim(Player.nickname)) == func.lower(func.trim(nickname)))
            result_p = await session.execute(stmt_p)
            player_obj = result_p.scalar_one_or_none()
            
            if player_obj and player_obj.user_id and player_obj.user_id != target_user_id:
                # Double check the User exists
                stmt_u = select(User).filter_by(id=player_obj.user_id)
                res_u = await session.execute(stmt_u)
                if res_u.scalar_one_or_none():
                    return {"status": "error", "message": "Персонаж уже закреплен за другим участником в базе игроков."}

            if player_obj:
                # Known character, link immediately
                if char:
                    char.user_id = target_user_id
                else:
                    char = Character(user_id=target_user_id, nickname=nickname, is_main=False)
                    session.add(char)
                
                # Sync to players
                player_obj.user_id = target_user_id
                await session.commit()
                return {"status": "ok", "message": "Персонаж успешно привязан"}
            else:
                # Unknown character, send approval request to Master
                user = await session.get(User, target_user_id)
                if not user:
                    return {"status": "error", "message": "Пользователь не найден"}
                
                user.pending_request_nick = nickname
                await session.commit()
                
                # Notify Masters
                try:
                    from loader import bot
                    from aiogram import types
                    stmt_m = select(User).filter_by(is_master=True)
                    masters = (await session.execute(stmt_m)).scalars().all()
                    
                    user_desc = f"@{user.username}" if user.username else f"ID {user.telegram_id}"
                    text = f"🛡 <b>Заявка на добавление (с сайта):</b>\n"
                    text += f"Игрок: {user_desc}\n"
                    text += f"Ник: <code>{nickname}</code>\n"
                    text += "⚠️ <i>Этого ника нет в базе. Требуется подтверждение.</i>"
                    
                    kb = types.InlineKeyboardMarkup(inline_keyboard=[
                        [types.InlineKeyboardButton(text="✅ Принять", callback_data=f"appr:ok:{user.id}:web_add:{nickname}")],
                        [types.InlineKeyboardButton(text="✏️ Исправить и принять", callback_data=f"appr:edit:{user.id}:web_add")],
                        [types.InlineKeyboardButton(text="❌ Отказать", callback_data=f"appr:no:{user.id}")],
                    ])
                    
                    for m in masters:
                        try:
                            await bot.send_message(m.telegram_id, text, parse_mode="HTML", reply_markup=kb)
                        except Exception: pass
                except Exception as e:
                    logging.error(f"Error notifying masters: {e}")
                
                return {"status": "pending", "message": "Заявка отправлена Мастеру"}

    except Exception as e:
        logging.error(f"Error in char_link: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/character/unlink")
async def char_unlink(request: Request):
    try:
        data = await request.json()
        role_id = data.get("role_id")
        nickname = data.get("nickname")

        async with AsyncSessionLocal() as session:
            if role_id:
                p_stmt = update(Player).where(Player.role_id == role_id).values(user_id=None)
                await session.execute(p_stmt)
                
                # Find nickname to delete from characters
                player = await session.get(Player, role_id)
                if player:
                    nickname = player.nickname

            if nickname:
                nickname = nickname.strip()
                # Delete from characters
                c_stmt = delete(Character).where(func.lower(func.trim(Character.nickname)) == func.lower(func.trim(nickname)))
                await session.execute(c_stmt)
                
                # Unlink from players
                p_stmt_io = update(Player).where(func.lower(func.trim(Player.nickname)) == func.lower(func.trim(nickname))).values(user_id=None)
                await session.execute(p_stmt_io)

            await session.commit()
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
             
        async with AsyncSessionLocal() as session:
            return await party_manager.get_party(session, role_id)
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

        async with AsyncSessionLocal() as session:
            from database import Player, PartyMember
            # Find new member by nickname
            stmt_member = select(Player).filter_by(nickname=member_nickname)
            res_member = await session.execute(stmt_member)
            member_row = res_member.scalar_one_or_none()

            if not member_row:
                return {"status": "error", "message": f"Игрок '{member_nickname}' не найден"}

            member_role_id = member_row.role_id

            # Check if member already in THIS party
            stmt_pm = select(PartyMember).filter_by(party_id=party_id, player_role_id=member_role_id)
            res_pm = await session.execute(stmt_pm)
            if res_pm.scalar_one_or_none():
                return {"status": "error", "message": "Игрок уже состоит в этой КП"}
            
            # Add to party
            new_member = PartyMember(party_id=party_id, player_role_id=member_role_id, is_leader=False)
            session.add(new_member)
            await session.commit()

        return {"status": "ok", "message": f"Игрок {member_nickname} добавлен в КП"}
    except Exception as e:
        logging.error(f"Error in party_add_member: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/party/add")
async def party_add(request: Request):
    """Add a player to party. Creates party if needed."""
    try:
        data = await request.json()
        leader_role_id = data.get("leader_role_id")
        member_nickname = data.get("nickname")
        logging.info(f"API party_add: leader_role_id={leader_role_id}, nickname={member_nickname}")

        if not leader_role_id or not member_nickname:
            return {"status": "error", "message": "Missing fields"}

        async with AsyncSessionLocal() as session:
            return await party_manager.add_to_party(session, leader_role_id, member_nickname)
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

        async with AsyncSessionLocal() as session:
            return await party_manager.remove_from_party(session, member_role_id)
    except Exception as e:
        logging.error(f"Error in party_remove: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.post("/party/rename")
async def party_rename(request: Request):
    """Rename a party."""
    try:
        data = await request.json()
        party_id = data.get("party_id")
        new_name = data.get("name", "").strip() or None

        if not party_id:
            return {"status": "error", "message": "party_id required"}

        async with AsyncSessionLocal() as session:
            return await party_manager.rename_party(session, party_id, new_name)
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

        async with AsyncSessionLocal() as session:
            return await party_manager.update_party_color(session, party_id, color)
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

        async with AsyncSessionLocal() as session:
            return await party_manager.remove_from_party(session, member_role_id)
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

        async with AsyncSessionLocal() as session:
            return await party_manager.transfer_leadership(session, party_id, new_leader_role_id)
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

        async with AsyncSessionLocal() as session:
            result = await update_player_logic(session, role_id, data)
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

        async with AsyncSessionLocal() as session:
            player = await session.get(Player, role_id)
            if not player:
                return {"status": "error", "message": f"Player ID {role_id} not found"}

            player.nickname = nickname if nickname else None
            await session.commit()

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

        async with AsyncSessionLocal() as session:
            player = await session.get(Player, role_id)
            if not player:
                return {"status": "error", "message": f"Player ID {role_id} not found"}

            player.class_id = class_id
            await session.commit()

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

        async with AsyncSessionLocal() as session:
            player = await session.get(Player, role_id)
            if not player:
                return {"status": "error", "message": f"Player ID {role_id} not found"}

            player.in_clan = in_clan_val
            await session.commit()

        return {"status": "ok", "message": f"Status updated for ID {role_id} to {in_clan_val}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/update_event_date")
async def update_event_date(request: Request):
    try:
        from database import Event
        data = await request.json()
        role_id = data.get("role_id")
        old_ts = int(data.get("old_timestamp"))
        new_date_str = data.get("new_date_str")
        msk_tz = pytz.timezone("Europe/Moscow")
        dt_naive = datetime.strptime(new_date_str, "%Y-%m-%d %H:%M:%S")
        new_ts = int(msk_tz.localize(dt_naive).timestamp())
        async with AsyncSessionLocal() as session:
            stmt = update(Event).where(Event.role_id == role_id, Event.timestamp == old_ts).values(timestamp=new_ts, event_date=new_date_str)
            await session.execute(stmt)
            await session.commit()
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)}
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
    try:
        from database import Event
        from sqlalchemy import select
        data = await request.json()
        role_id, d_str, val = data.get("role_id"), data.get("date"), data.get("value")
        msk_tz = pytz.timezone("Europe/Moscow")
        dt_naive = datetime.strptime(d_str.replace("T", " "), "%Y-%m-%d %H:%M:%S" if len(d_str)>16 else "%Y-%m-%d %H:%M")
        ts = int(msk_tz.localize(dt_naive).timestamp())
        async with AsyncSessionLocal() as session:
            # Check for existing
            stmt_check = select(Event).filter_by(
                role_id=role_id,
                timestamp=ts,
                event_type=1,
                value=int(val)
            )
            res_check = await session.execute(stmt_check)
            if res_check.scalar_one_or_none():
                return {"status": "ok", "message": "Duplicate event skipped"}

            ev = Event(role_id=role_id, timestamp=ts, event_date=d_str, event_type=1, value=int(val), raw_desc=data.get("description", ""))
            session.add(ev)
            await session.commit()
            return {"status": "ok", "message": "Event added"}
    except Exception as e: return {"status": "error", "message": str(e)}
@router.post("/add_event_bulk")
async def add_event_bulk(request: Request):
    try:
        from database import Event
        from sqlalchemy import select
        data = await request.json()
        ids, d_str, val = data.get("role_ids"), data.get("date"), data.get("value")
        msk_tz = pytz.timezone("Europe/Moscow")
        dt_naive = datetime.strptime(d_str.replace("T", " "), "%Y-%m-%d %H:%M:%S" if len(d_str)>16 else "%Y-%m-%d %H:%M")
        ts = int(msk_tz.localize(dt_naive).timestamp())
        async with AsyncSessionLocal() as session:
            added_count = 0
            skipped_count = 0
            for rid in ids:
                # Check for existing
                stmt_check = select(Event).filter_by(
                    role_id=rid,
                    timestamp=ts,
                    event_type=1,
                    value=int(val)
                )
                res_check = await session.execute(stmt_check)
                if res_check.scalar_one_or_none():
                    skipped_count += 1
                    continue

                ev = Event(role_id=rid, timestamp=ts, event_date=d_str, event_type=1, value=int(val), raw_desc=data.get("description", ""))
                session.add(ev)
                added_count += 1
            await session.commit()
        return {"status": "ok", "message": f"Events added: {added_count}, skipped: {skipped_count}"}
    except Exception as e: return {"status": "error", "message": str(e)}
@router.post("/delete_event")
async def delete_event(request: Request):
    try:
        from database import Event
        data = await request.json()
        event_id = data.get("event_id")
        if not event_id:
            return {"status": "error", "message": "Missing event_id"}
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Event).where(Event.id == int(event_id)))
            await session.commit()
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)}


@router.post("/master/announce")
async def master_announce(request: Request):
    """Create a new broadcast announcement."""
    try:
        from database import ScheduledAnnouncement
        from loader import bot
        from handlers.admin import schedule_job
        
        data = await request.json()
        text = data.get("text")
        schedule_type = data.get("schedule_type")
        run_time = data.get("run_time", "")
        days_of_week = data.get("days_of_week", "")
        
        if not text or not schedule_type:
            return {"status": "error", "message": "Text and schedule type are required"}
            
        async with AsyncSessionLocal() as session:
            ann = ScheduledAnnouncement(
                text=text,
                schedule_type=schedule_type,
                run_time=run_time,
                days_of_week=days_of_week,
                is_active=True
            )
            session.add(ann)
            await session.commit()
            
            # Immediately run or schedule
            if schedule_type == "now":
                from handlers.admin import run_broadcast
                import asyncio
                # Run it asynchronously
                asyncio.create_task(run_broadcast(ann.id, bot))
            else:
                schedule_job(ann, bot)
                
            return {"status": "ok", "message": "Объявление успешно создано/запланировано"}
            
    except Exception as e:
        import logging
        logging.error(f"Error in master_announce: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@router.get("/master/announcements")
async def master_announcements(request: Request):
    """Get active scheduled announcements."""
    try:
        from database import ScheduledAnnouncement
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ScheduledAnnouncement).filter_by(is_active=True).order_by(ScheduledAnnouncement.id.desc())
            )
            anns = result.scalars().all()
            return {
                "status": "ok", 
                "announcements": [{
                    "id": a.id,
                    "text": a.text,
                    "schedule_type": a.schedule_type,
                    "run_time": a.run_time,
                    "days_of_week": a.days_of_week
                } for a in anns]
            }
    except Exception as e:
        import logging
        logging.error(f"Error in master_announcements: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@router.post("/master/announcements/delete")
async def master_announcements_delete(request: Request):
    """Delete (deactivate) an active announcement."""
    try:
        from database import ScheduledAnnouncement
        from loader import scheduler
        data = await request.json()
        ann_id = data.get("id")
        if not ann_id: return {"status": "error", "message": "ID required"}
        
        async with AsyncSessionLocal() as session:
            ann = await session.get(ScheduledAnnouncement, ann_id)
            if ann:
                ann.is_active = False
                await session.commit()
                
        # Remove from scheduler
        job_id = f"ann_{ann_id}"
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass # Job might not exist, already ran, or was a 'once_now'
            
        return {"status": "ok"}
    except Exception as e:
        import logging
        logging.error(f"Error in master_announcements_delete: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
