import asyncio
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
from logic.player_manager import update_player_logic, get_player_profile
from logic import reward_ops
from sqlalchemy import func
from database import session, QueueType, RewardHistory, User

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

# --- Master Panel Endpoints ---

@router.get("/master/queues")
async def master_get_queues():
    """Get list of active queues for Master Panel."""
    try:
        queues = session.query(QueueType).filter_by(is_active=True).all()
        result = []
        for q in queues:
            # Need queue details including count. The admin.py handles logic.queue_ops.get_admin_queue_count.
            # We import here to avoid circular or too early imports, or reuse if already available.
            from logic.queue_ops import get_admin_queue_count
            count = get_admin_queue_count(session, q.id)
            result.append({"id": q.id, "name": q.name, "count": count, "is_locked": q.is_locked, "description": q.description})
            
        pending_count = session.query(RewardHistory).filter_by(is_notified=False).count()
        return {"status": "ok", "queues": result, "pending_notifications": pending_count}
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
        from database import get_msk_now
        
        entries = get_admin_queue_entries(session, queue_id)
        
        nicks = [e.character_name for e in entries]
        valor_map = get_weekly_valor_map(nicks)
        
        # Get class IDs for these nicks
        from database import Player
        # SQLite's LOWER() doesn't work for Cyrillic. 
        # We fetch exact matches and then build map in Python for normalized lookup.
        players = session.query(Player).filter(Player.nickname.in_(nicks)).all()
        player_map = {p.nickname.lower(): p.class_id for p in players}
        
        now = get_msk_now()
        
        result_entries = []
        for e in entries:
            val = valor_map.get(e.character_name, -1)
            class_id = player_map.get(e.character_name.lower(), -1)
            
            is_afk = False
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

@router.post("/master/issue_reward")
async def master_issue_reward(request: Request):
    """Issue reward to an entry ID."""
    try:
        data = await request.json()
        entry_id = data.get("entry_id")
        master_id = data.get("master_id") # We need master role id or user id
        
        if not entry_id or not master_id:
            return {"status": "error", "message": "Missing entry_id or master_id"}
            
        # Get master user info from role ID
        master = session.query(User).filter_by(id=master_id).first()
        if not master or not master.is_master:
            # Let's fallback to checking if the ID given might be a role ID
            async with aiosqlite.connect(web_database.DB_NAME) as conn:
                async with conn.execute("SELECT user_id FROM players WHERE role_id = ?", (master_id,)) as cursor:
                    m_row = await cursor.fetchone()
                    if m_row and m_row[0]:
                        master = session.query(User).filter_by(id=m_row[0]).first()
            if not master or not master.is_master:
                return {"status": "error", "message": "Unauthorized or not found."}
                
        # To call issue_reward, we need original QueueEntry details before it's deleted
        from database import QueueEntry
        # Re-fetch entry to securely capture q_name, main_nick, char_nick
        entry = session.get(QueueEntry, entry_id)
        if not entry:
            return {"status": "error", "message": "Уже выдано/удалено."}
            
        q_name = entry.queue.name
        char_nick = entry.character_name
        
        main_nick = char_nick
        user = entry.user
        if user:
            from database import Character
            main_char = session.query(Character).filter_by(user_id=user.id, is_main=True).first()
            if main_char:
                main_nick = main_char.nickname
                
        success, msg, hist = reward_ops.issue_reward(session, entry_id, master.username)
        
        if success:
            from utils import log_reward_to_sheet
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
            
        master = session.query(User).filter_by(id=master_id).first()
        if not master or not master.is_master:
            # Fallback handling
            async with aiosqlite.connect(web_database.DB_NAME) as conn:
                async with conn.execute("SELECT user_id FROM players WHERE role_id = ?", (master_id,)) as cursor:
                    m_row = await cursor.fetchone()
                    if m_row and m_row[0]:
                        master = session.query(User).filter_by(id=m_row[0]).first()
            if not master or not master.is_master:
                return {"status": "error", "message": "Unauthorized or not found."}
                
        success, msg, hist = reward_ops.warn_user(session, entry_id, master.username)
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
        from keyboards import get_back_btn
        from database import RewardHistory, User, session
        
        pending = session.query(RewardHistory).filter_by(is_notified=False).all()
        if not pending:
            return {"status": "error", "message": "Нет уведомлений для отправки."}
            
        user_map = {}
        for item in pending:
            if item.user_id not in user_map:
                user_map[item.user_id] = []
            user_map[item.user_id].append(item)
            
        count_users = 0
        for uid, items in user_map.items():
            user = session.get(User, uid)
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
                
        session.commit()
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
        for idx, eid in enumerate(entry_ids):
            entry = session.get(QueueEntry, eid)
            if entry:
                entry.position = idx
        session.commit()
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
        entry = session.get(QueueEntry, entry_id)
        if entry:
            session.delete(entry)
            session.commit()
            return {"status": "ok", "message": "Игрок удален из очереди"}
        return {"status": "error", "message": "Запись не найдена"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/master/search_players")
async def master_search_players(request: Request):
    """Search for players by nickname and optional class_id."""
    try:
        data = await request.json()
        query = data.get("query", "").strip().lower()
        class_id = data.get("class_id")
        
        from database import Player
        db_query = session.query(Player)
        
        if class_id is not None and class_id != -1:
            db_query = db_query.filter(Player.class_id == class_id)
            
        # SQLite ILIKE is not case-insensitive for Cyrillic/Unicode characters.
        # We fetch all (or filtered by class) and filter in Python.
        players = db_query.all()
        
        result = []
        for p in players:
            nick = p.nickname if p.nickname else ""
            if not query or query in nick.lower():
                result.append({
                    "nickname": nick,
                    "class_id": p.class_id,
                    "has_telegram": p.user_id is not None,
                    "user_id": p.user_id,
                    "role_id": p.role_id
                })
        
        result.sort(key=lambda x: x["nickname"])
        return {"status": "ok", "players": result[:50]}
    except Exception as e:
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
        # Find player by nick
        # 1. Try exact case-sensitive match (best for special/Cyrillic chars)
        player = session.query(Player).filter(Player.nickname == char_name).first()
        
        if not player:
            # 2. Try case-insensitive fallback (SQLite lower handles ASCII only, but we check Python side)
            # Find all potential matches and check in Python
            all_players = session.query(Player).all()
            target_low = char_name.lower()
            for p in all_players:
                if p.nickname and p.nickname.lower() == target_low:
                    player = p
                    break
        
        user_id = None
        if player:
            user_id = player.user_id
        else:
            # Check characters table too (Exact match first)
            char = session.query(Character).filter(Character.nickname == char_name).first()
            if not char:
                # Case-insensitive fallback for Character
                all_chars = session.query(Character).all()
                for c in all_chars:
                    if c.nickname and c.nickname.lower() == char_name.lower():
                        char = c
                        break
            
            if char:
                user_id = char.user_id
            else:
                return {"status": "error", "message": f"Игрок '{char_name}' не найден в базе гильдии."}
        
        # Check if already in queue (either specific nick or same user)
        if user_id:
            existing = session.query(QueueEntry).filter_by(queue_type_id=queue_id, user_id=user_id).first()
            if existing:
                return {"status": "error", "message": f"Основа или твин этого игрока ({existing.character_name}) уже в очереди."}
        else:
            # No user_id (not in TG), just check exact nickname
            existing = session.query(QueueEntry).filter_by(queue_type_id=queue_id, character_name=char_name).first()
            if existing:
                return {"status": "error", "message": "Данный никнейм уже в этой очереди."}

        # Get max position
        max_pos = session.query(func.max(QueueEntry.position)).filter_by(queue_type_id=queue_id).scalar() or 0
        
        new_entry = QueueEntry(
            user_id=user_id,
            queue_type_id=queue_id,
            character_name=char_name,
            position=max_pos + 1,
            auto_requeue=auto_requeue
        )
        session.add(new_entry)
        session.commit()
        return {"status": "ok", "message": f"Игрок {char_name} добавлен"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/master/settings")
async def master_get_settings():
    """Get global master settings."""
    try:
        from database import get_setting
        default_limit = get_setting("default_limit", "1")
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
            set_setting("default_limit", str(default_limit))
            return {"status": "ok", "message": "Настройки обновлены"}
        return {"status": "error", "message": "No settings to update"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/master/user_limit")
async def master_update_user_limit(request: Request):
    """Set personal limit for a user (via user_id or role_id)."""
    try:
        data = await request.json()
        user_id = data.get("user_id")
        role_id = data.get("role_id")
        limit = data.get("limit")  # Can be None to clear

        if user_id is None and role_id is None:
            return {"status": "error", "message": "user_id or role_id is required"}

        from database import Player, User, Character

        user = None
        if user_id is not None:
            user = session.get(User, user_id)
        
        if not user and role_id is not None:
            # Check if this player is already linked to a user
            player = session.get(Player, role_id)
            if player and player.user_id:
                user = session.get(User, player.user_id)
            elif player:
                # Create a shadow user or just link if they register later?
                # For now, let's create a User record if it doesn't exist to store the limit
                user = User(username=player.nickname, is_master=False)
                session.add(user)
                session.flush() # Get id
                player.user_id = user.id
                
        if not user:
            return {"status": "error", "message": "Пользователь не найден"}

        user.personal_limit = limit
        session.commit()
        return {"status": "ok", "message": "Лимит обновлен"}
    except Exception as e:
        session.rollback()
        return {"status": "error", "message": str(e)}


@router.get("/master/user_limits")
async def master_get_user_limits():
    """Get list of users who have a personal limit set."""
    try:
        from database import User, Player, Character
        users = session.query(User).filter(User.personal_limit.isnot(None)).all()
        result = []
        for u in users:
            # Try to find a nickname from players table preferentially
            player = session.query(Player).filter_by(user_id=u.id).first()
            char_name = player.nickname if player else u.username
            
            # Fallback to characters table
            if not player:
                main_char = session.query(Character).filter_by(user_id=u.id, is_main=True).first()
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

        queue = session.get(QueueType, queue_id)
        if not queue:
            return {"status": "error", "message": "Очередь не найдена"}

        queue.description = description
        session.commit()
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

        queue = session.get(QueueType, queue_id)
        if not queue:
            return {"status": "error", "message": "Очередь не найдена"}

        queue.is_locked = bool(is_locked)
        session.commit()
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
        db_query = session.query(RewardHistory)
        if queue_name:
            db_query = db_query.filter(RewardHistory.queue_name.ilike(f"%{queue_name}%"))
        if character_name:
            db_query = db_query.filter(RewardHistory.character_name.ilike(f"%{character_name}%"))
        if issued_by:
            db_query = db_query.filter(RewardHistory.issued_by.ilike(f"%{issued_by}%"))
            
        total = db_query.count()
        records = db_query.order_by(RewardHistory.timestamp.desc()).limit(limit).offset(offset).all()
        
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
        queues = [r[0] for r in session.query(RewardHistory.queue_name).distinct().all() if r[0]]
        characters = [r[0] for r in session.query(RewardHistory.character_name).distinct().all() if r[0]]
        masters = [r[0] for r in session.query(RewardHistory.issued_by).distinct().all() if r[0]]
        
        return {
            "status": "ok",
            "queues": sorted(queues),
            "characters": sorted(characters),
            "masters": sorted(masters)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.delete("/master/reward_history/{record_id}")
async def master_delete_reward_history(record_id: int):
    """Delete a specific reward history record."""
    try:
        record = session.get(RewardHistory, record_id)
        if not record:
            return {"status": "error", "message": "Запись не найдена"}
            
        session.delete(record)
        session.commit()
        return {"status": "ok", "message": "Запись удалена"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


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
        # Wait to int cast until we know it's not None
        old_ts_raw = data.get("old_timestamp")
        new_date_str = data.get("new_date_str")  # "YYYY-MM-DD HH:MM:SS"

        if not role_id or not old_ts_raw or not new_date_str:
            return {"status": "error", "message": "Missing params"}

        try:
            old_ts = int(old_ts_raw)
        except ValueError:
            return {"status": "error", "message": "Invalid old_timestamp"}

        # Calculate new timestamp from string (assuming input is MSK)
        # Parse logic:
        try:
            # Assume input format YYYY-MM-DD HH:MM:SS
            dt_naive = datetime.strptime(new_date_str, "%Y-%m-%d %H:%M:%S")
            dt_msk = msk_tz.localize(dt_naive)
            new_ts = int(dt_msk.timestamp())
        except Exception as date_e:
            return {"status": "error", "message": f"Invalid date format: {date_e}"}

        # Check against current time
        current_msk = datetime.now(msk_tz)
        if new_ts > int(current_msk.timestamp()):
            return {"status": "error", "message": "Новая дата не может быть из будущего"}

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

        # Check against current time
        current_msk = datetime.now(msk_tz)
        if timestamp > int(current_msk.timestamp()):
            return {"status": "error", "message": "Событие не может быть из будущего"}

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


@router.post("/add_event_bulk")
async def add_event_bulk(request: Request):
    """
    API endpoint to manually add an event (Valor) to multiple players at once.
    """
    try:
        msk_tz = pytz.timezone("Europe/Moscow")

        data = await request.json()
        role_ids = data.get("role_ids")
        if not isinstance(role_ids, list) or not role_ids:
            return {"status": "error", "message": "role_ids must be a non-empty list"}

        event_date_str = data.get("date")  # "YYYY-MM-DD HH:MM:SS" (MSK)
        value = data.get("value")
        description = data.get("description", "")

        if not event_date_str or value is None:
            return {"status": "error", "message": "Missing date or value"}

        try:
            val_int = int(value)
        except Exception:
            return {"status": "error", "message": "Value must be an integer"}

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

        # Check against current time
        current_msk = datetime.now(msk_tz)
        if timestamp > int(current_msk.timestamp()):
            return {"status": "error", "message": "Событие не может быть из будущего"}

        logging.info(f"Bulk Event Add: {len(role_ids)} players, val={val_int}, ts={timestamp} ({event_date_str})")

        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            # Prepare data
            insert_data = [
                (role_id, timestamp, event_date_str, 1, val_int, description)
                for role_id in role_ids
            ]

            # We don't strictly assert every player ID exists here to speed up bulk insert, 
            # foreign keys (if strict) or just raw insertion is fine for logging events 
            # (especially since UI selects from existing profiles).
            await conn.executemany(
                """
                INSERT INTO events (role_id, timestamp, event_date, event_type, value, raw_desc)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                insert_data,
            )

            await conn.commit()

        return {"status": "ok", "message": f"Event added successfully to {len(role_ids)} players"}

    except Exception as e:
        logging.error(f"Error in add_event_bulk: {e}", exc_info=True)
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
