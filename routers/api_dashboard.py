from datetime import datetime, timedelta
from typing import List, Optional, Any
import os

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text, func
from sqlalchemy.orm import selectinload

from consts import CLASSES
from database import User, AsyncSessionLocal, Player, get_session
from sqlalchemy.ext.asyncio import AsyncSession
from web_database import get_last_update_time
from logic.dashboard import get_kh_table_data, get_history_data, get_money_table_data
from auth_helper import validate_init_data

BOT_TOKEN = os.getenv("BOT_TOKEN")

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# Models for Admin Settings
class AdminSettings(BaseModel):
    public_log_enabled: bool
    public_log_channel_id: str
    public_log_thread_id: str
    verification_code: str

class BackupFile(BaseModel):
    name: str
    size_mb: float
    mtime: float


# --- Models ---

class UserData(BaseModel):
    id: int
    telegram_id: Optional[int] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    is_master: bool
    is_banned: bool
    main_role_id: Optional[int] = None
    pending_request_nick: Optional[str] = None

class InitResponse(BaseModel):
    user: Optional[UserData]
    classes: dict
    queue_types: List[dict]
    last_updated: str
    bot_username: str

class KHTableRow(BaseModel):
    role_id: int
    name: str
    class_id: int
    user_id: Optional[int] = None
    is_alt: bool = False
    cp_id: Optional[int] = None
    cp_color: Optional[str] = None
    s1: int = 0
    s2: int = 0
    s3: int = 0
    s4: int = 0
    s5: int = 0
    s6: int = 0
    s7: int = 0
    adepts: int = 0
    dances: int = 0
    total_valor: int
    total_gold: int
    is_mine: bool
    is_newcomer: bool
    is_afk: bool
    afk_dates: Optional[str]
    afk_reason: Optional[str] = None
    join_date: str
    join_days_ago: int
    valor_tier: str
    gold_tier: str
    s1_details: Optional[List[str]] = []
    s2_details: Optional[List[str]] = []
    s3_details: Optional[List[str]] = []
    s4_details: Optional[List[str]] = []
    s5_details: Optional[List[str]] = []
    s6_details: Optional[List[str]] = []
    s7_details: Optional[List[str]] = []
    adepts_details: Optional[List[str]] = []
    dances_details: Optional[List[str]] = []
    main_nickname: Optional[str] = None
    parties: Optional[List[dict]] = []

class KHResponse(BaseModel):
    rows: List[KHTableRow]
    start_date: str
    end_date: str

class HistoryRow(BaseModel):
    date: str
    name: Optional[str]
    class_id: int
    class_name: str
    desc: str
    type: int
    role_id: int
    item_name: Optional[str]
    is_mine: bool
    is_afk: bool
    afk_dates: Optional[str]
    afk_reason: Optional[str] = None
    join_date: Optional[str] = None
    join_days_ago: Optional[int] = 0
    timestamp: float
    id: int

class ProfileAfkHistory(BaseModel):
    id: int
    start: Optional[str] = None
    end: Optional[str] = None
    reason: Optional[str] = None

class ProfileQueue(BaseModel):
    id: int
    name: str
    auto_requeue: bool
    character_name: Optional[str]

class KHPeriodStats(BaseModel):
    s1: int = 0
    s2: int = 0
    s3: int = 0
    s4: int = 0
    s5: int = 0
    s6: int = 0
    s7: int = 0
    adepts: int = 0
    dances: int = 0
    total_valor: int = 0

class KHStatsSummary(BaseModel):
    day: KHPeriodStats
    week: KHPeriodStats
    month: KHPeriodStats

class ProfileLinkedChar(BaseModel):
    nickname: str
    is_main: bool
    class_id: Optional[int] = 0
    role_id: Optional[int] = None
    kh_stats: Optional[KHStatsSummary] = None

class ProfilePartyMember(BaseModel):
    nickname: Optional[str]
    is_leader: bool
    class_id: int
    role_id: int

class ProfileParty(BaseModel):
    id: int
    name: Optional[str]
    color: Optional[str] = None
    is_leader: bool
    members: List[ProfilePartyMember]

class SquadKHCharStats(BaseModel):
    role_id: int
    nickname: str
    stats: KHPeriodStats

class SquadKHStatsResponse(BaseModel):
    period: str
    offset: int
    start_date: str
    end_date: str
    squad_stats: List[SquadKHCharStats]

class NicknameUpdateRequest(BaseModel):
    nickname: str

class ProfileEvent(BaseModel):
    id: int
    timestamp: int
    date: str
    type: int
    value: int
    description: Optional[str]

class ProfileResponse(BaseModel):
    role_id: int
    nickname: Optional[str]
    class_id: int
    in_clan: bool
    is_alt: bool
    user_id: Optional[int]
    telegram_id: Optional[int]
    username: Optional[str]
    afk_start: Optional[str]
    afk_end: Optional[str]
    afk_reason: Optional[str] = None
    afk_history: List[ProfileAfkHistory]
    queues: List[ProfileQueue]
    linked_chars: List[ProfileLinkedChar]
    parties: List[ProfileParty] = []
    party: Optional[ProfileParty]
    events: List[ProfileEvent] = []
    kh_stats: Optional[KHStatsSummary] = None
    pending_request_nick: Optional[str] = None

class CPListItem(BaseModel):
    id: int
    name: Optional[str]
    leader_nickname: Optional[str]
    member_count: int

class CPApplicationRequest(BaseModel):
    party_id: int

class CPApplicationItem(BaseModel):
    application_id: int
    applicant_role_id: int
    applicant_nickname: Optional[str]
    applicant_class_id: int
    created_at: str

class CPResolveRequest(BaseModel):
    application_id: int
    action: str  # 'accept' or 'reject'

class CPCreateRequest(BaseModel):
    name: Optional[str] = None

class CPAddMemberRequest(BaseModel):
    party_id: int
    nickname: str

class SetMainRequest(BaseModel):
    new_main_role_id: int


# --- Helpers ---

async def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    
    # Fallback to TMA header if session is missing
    if not user_id:
        init_data = request.headers.get("X-Telegram-Init-Data")
        if init_data and BOT_TOKEN:
            try:
                parsed = validate_init_data(init_data, BOT_TOKEN)
                if parsed.get("user"):
                    user_id = parsed["user"]["id"]
            except Exception:
                pass

    if not user_id:
        return None
        
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(User).options(selectinload(User.characters)).filter_by(telegram_id=user_id)
        )
        return result.scalars().first()

class FaqMessageBase(BaseModel):
    text: Optional[str] = None
    photo_id: Optional[str] = None
    order_index: int = 0

class FaqMessageResponse(FaqMessageBase):
    id: int
    topic_id: int

class FaqTopicBase(BaseModel):
    topic: str

class FaqTopicCreate(FaqTopicBase):
    initial_messages: List[FaqMessageBase] = []

class FaqTopicResponse(FaqTopicBase):
    id: int
    content: Optional[str] = None
    updated_at: datetime
    message_count: int

# --- API ENDPOINTS ---

@router.get("/init", response_model=InitResponse)
async def get_init_data(request: Request):
    user = await get_current_user(request)
    last_upd = await get_last_update_time()
    
    # Fetch active queue types
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(text("SELECT id, name, description FROM queue_types WHERE is_active = TRUE"))
        queue_types = [dict(r) for r in result.mappings().all()]

    user_data = None
    if user:
        # Find main character role ID
        async with AsyncSessionLocal() as db_session_internal:
            res_m = await db_session_internal.execute(
                select(Player.role_id).where(Player.user_id == user.id, Player.is_alt == False)
            )
            main_role_id = res_m.scalars().first()
            
            # Fallback if no explicit main found, take first available role
            if not main_role_id:
                res_f = await db_session_internal.execute(
                    select(Player.role_id).where(Player.user_id == user.id).limit(1)
                )
                main_role_id = res_f.scalars().first()

        import logging
        logging.getLogger("uvicorn.error").warning(f"DEBUG: get_init_data user={user.id} tg={user.telegram_id}")
        user_data = UserData(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username or "Unknown",
            avatar_url=user.avatar_url,
            is_master=user.is_master,
            is_banned=user.is_banned,
            main_role_id=main_role_id,
            pending_request_nick=user.pending_request_nick
        )

    return InitResponse(
        user=user_data,
        classes=CLASSES,
        queue_types=queue_types,
        last_updated=last_upd,
        bot_username=os.getenv("BOT_USERNAME", "Lineage2_Guild_Bot")
    )

@router.get("/kh", response_model=KHResponse)
async def get_kh_data(
    request: Request,
    start: Optional[str] = None,
    end: Optional[str] = None,
    classes: Optional[str] = None, # Comma separated
    newcomers: Optional[str] = None
):
    user = await get_current_user(request)
    my_nicks = {c.nickname.lower().strip() for c in user.characters if c.nickname} if user else set()

    # Classes
    class_list = [int(x) for x in classes.split(",")] if classes else None

    data = await get_kh_table_data(start, end, class_list, newcomers, my_nicks)
    
    # Transform dicts to Pydantic models if needed (FastAPI usually handles dict->model automatically)
    try:
        # Validate manually to catch errors
        resp = KHResponse(
            rows=data["rows"],
            start_date=data["start_date"],
            end_date=data["end_date"]
        )
        return resp
    except Exception as e:
        print(f"API VALIDATION ERROR: {e}")
        # Print first row to see what's wrong
        if data["rows"]:
            print(f"Sample Row: {data['rows'][0]}")
        raise e

@router.get("/money")
async def get_money_data(
    request: Request,
    start: Optional[str] = None,
    end: Optional[str] = None,
    classes: Optional[str] = None,
    newcomers: Optional[str] = None,
    group_period: Optional[str] = None,
    group_count: int = 1
):
    user = await get_current_user(request)
    my_nicks = {c.nickname.lower().strip() for c in user.characters if c.nickname} if user else set()

    class_list = [int(x) for x in classes.split(",")] if classes else None

    # Handle "Group by None" case
    gpt = group_period if (group_period and group_period != "") else None
    
    # Default to "day" if None passed (legacy UI logic, can be changed)
    if not gpt and group_period is None: 
         gpt = "day"

    data = await get_money_table_data(start, end, class_list, newcomers, gpt, group_count, my_nicks)
    return data # Returns dict, FastAPI validates automagically usually, or stick to models if needed

@router.get("/history", response_model=List[HistoryRow])
async def get_history_endpoint(
    request: Request,
    start: Optional[str] = None,
    end: Optional[str] = None,
    classes: Optional[str] = None,
    types: Optional[str] = None
):
    user = await get_current_user(request)
    my_nicks = {c.nickname.lower().strip() for c in user.characters if c.nickname} if user else set()

    class_list = [int(x) for x in classes.split(",")] if classes else None
    type_list = types.split(",") if types else None

    rows = await get_history_data(start, end, class_list, type_list, my_nicks)
    return rows

@router.get("/profile/{role_id}", response_model=ProfileResponse)
async def get_profile_endpoint(role_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    # Dynamic import to avoid circular dependency if any (though logic modules usually okay)
    from logic.player_manager import get_player_profile
    data = await get_player_profile(session, role_id)
    if not data:
         # Return empty or error? Better 404 but for now valid empty struct
         # Actually let's return 404 if not found
         from fastapi import HTTPException
         raise HTTPException(status_code=404, detail="Player not found")
    
    # helper to safe convert dates to ISO string for ProfileResponse
    from datetime import datetime
    if data.get("afk_start") and isinstance(data["afk_start"], datetime):
        data["afk_start"] = data["afk_start"].strftime("%Y-%m-%d")
    if data.get("afk_end") and isinstance(data["afk_end"], datetime):
        data["afk_end"] = data["afk_end"].strftime("%Y-%m-%d")
    
    # Add pending request nick
    if user and (user.is_master or user.id == data.get("user_id")):
        data["pending_request_nick"] = user.pending_request_nick

    return data

@router.post("/profile/{role_id}")
async def update_profile_endpoint(role_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user:
         from fastapi import HTTPException
         raise HTTPException(status_code=401, detail="Unauthorized")

    # Permission check: Master can edit anyone, User can edit their own characters
    can_edit = user.is_master
    if not can_edit:
        # Check ownership
        # Now check if the current user owns a character with this player's nickname
        from database import Player, Character
        player_result = await session.execute(select(Player).filter_by(role_id=role_id))
        player_row = player_result.scalars().first()

        if player_row:
            char_row = await session.execute(select(Character).filter_by(user_id=user.id, nickname=player_row.nickname))
            char = char_row.scalars().first()
            if char:
                can_edit = True

    if not can_edit:
         from fastapi import HTTPException
         raise HTTPException(status_code=403, detail="Permission denied")

    body = await request.json()
    from logic.player_manager import update_player_logic
    
    try:
        result = await update_player_logic(session, role_id, body)
        return result
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/profile/{role_id}/squad_kh_stats", response_model=SquadKHStatsResponse)
async def get_squad_kh_stats(role_id: int, period: str = "week", offset: int = 0, session: AsyncSession = Depends(get_session)):
    from logic.player_manager import calculate_calendar_stats
    from database import Player, Character
    
    # 1. Get the main requested player
    stmt = select(Player.nickname).where(Player.role_id == role_id)
    res = await session.execute(stmt)
    main_nick = res.scalars().first()
    if not main_nick:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Player not found")
        
    # 2. Find all linked characters
    user_id_stmt = select(Character.user_id).where(func.lower(func.trim(Character.nickname)) == func.lower(func.trim(main_nick)))
    user_id_res = await session.execute(user_id_stmt)
    user_id_row = user_id_res.first()
    
    linked_chars = []
    if user_id_row and user_id_row.user_id:
        uid = user_id_row.user_id
        chars_stmt = select(Character.nickname).where(Character.user_id == uid)
        for c_row in (await session.execute(chars_stmt)).all():
            c_nick = c_row.nickname
            p_stmt = select(Player.role_id).where(func.lower(func.trim(Player.nickname)) == func.lower(func.trim(c_nick)))
            p_role_id = (await session.execute(p_stmt)).scalars().first()
            if p_role_id:
                linked_chars.append({"role_id": p_role_id, "nickname": c_nick})
    else:
        linked_chars.append({"role_id": role_id, "nickname": main_nick})

    squad_stats = []
    common_start = None
    common_end = None
    
    for char in linked_chars:
        try:
            char_data = await calculate_calendar_stats(session, char["role_id"], period, offset)
            if not common_start:
                common_start = char_data["start_date"]
                common_end = char_data["end_date"]
            squad_stats.append(SquadKHCharStats(
                role_id=char["role_id"],
                nickname=char["nickname"],
                stats=KHPeriodStats(**char_data["stats"])
            ))
        except Exception as e:
            logging.error(f"Error calculating stats for {char['nickname']}: {e}")
            
    return SquadKHStatsResponse(
        period=period,
        offset=offset,
        start_date=common_start or "",
        end_date=common_end or "",
        squad_stats=squad_stats
    )

@router.patch("/profile/{role_id}/linked_chars/{char_role_id}/nickname")
async def update_linked_char_nickname(role_id: int, char_role_id: int, req: NicknameUpdateRequest, request: Request, session: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    # Permission check: needs to be master to alter nicknames system-wide, or own them? 
    # Usually editing linked characters requires master or ownership.
    # We will enforce master for simplicity or ownership if they are linked to the user.
    can_edit = user.is_master
    from database import Player, Character
    
    if not can_edit:
        # check if char belongs to user
        p_stmt = select(Player.nickname).where(Player.role_id == role_id)
        p_nick = (await session.execute(p_stmt)).scalars().first()
        if p_nick:
             char_row = await session.execute(select(Character).filter_by(user_id=user.id, nickname=p_nick))
             if char_row.scalars().first():
                 can_edit = True

    if not can_edit:
         from fastapi import HTTPException
         raise HTTPException(status_code=403, detail="Permission denied")
         
    # Find old nickname to update in characters table
    p_stmt = select(Player.nickname).where(Player.role_id == char_role_id)
    old_nick = (await session.execute(p_stmt)).scalars().first()
    if not old_nick:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Player not found")
        
    c_stmt = select(Character).where(
        func.lower(func.trim(Character.nickname)) == func.lower(func.trim(old_nick))
    )
    character = (await session.execute(c_stmt)).scalars().first()
    if not character:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Character record not found. Link a character first.")
        
    character.nickname = req.nickname
    # Sync Player table
    stmt_p_sync = select(Player).where(Player.role_id == char_role_id)
    res_p_sync = await session.execute(stmt_p_sync)
    player_record = res_p_sync.scalars().first()
    if player_record:
        player_record.nickname = req.nickname
    await session.commit()
    return {"status": "ok", "message": "Nickname updated"}

@router.post("/profile/{role_id}/cancel_request")
async def cancel_pending_request_endpoint(role_id: int, request: Request, session: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Permission: User can cancel their own request
    cancelled_nick = user.pending_request_nick
    if not cancelled_nick:
        return {"status": "ok", "message": "No pending request"}
    
    user.pending_request_nick = None
    await session.commit()
    
    # Notify Masters
    try:
        from loader import bot
        from database import User as UserDB
        result = await session.execute(select(UserDB).filter_by(is_master=True))
        masters = result.scalars().all()
        user_desc = f"@{user.username}" if user.username else f"ID {user.telegram_id}"
        for m in masters:
            try:
                await bot.send_message(
                    m.telegram_id,
                    f"❌ <b>Пользователь отменил заявку через сайт!</b>\nИгрок: {user_desc}\nНик: {cancelled_nick}",
                    parse_mode="HTML",
                )
            except Exception:
                pass
    except Exception:
        pass

    return {"status": "ok", "message": "Request cancelled"}

@router.post("/profile/{role_id}/set_main")
async def set_main_character_endpoint(role_id: int, req: SetMainRequest, request: Request, session: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Permission check: Master or owner
    can_edit = user.is_master
    if not can_edit:
        # Check if the player being set as main belongs to the user
        from database import Player, Character
        p_stmt = select(Player.nickname).where(Player.role_id == req.new_main_role_id)
        p_nick = (await session.execute(p_stmt)).scalars().first()
        if p_nick:
            char_row = await session.execute(select(Character).filter_by(user_id=user.id, nickname=p_nick))
            if char_row.scalars().first():
                can_edit = True
    
    if not can_edit:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    from database import Character, Player
    # Get nickname of the new main
    p_stmt = select(Player.nickname).where(Player.role_id == req.new_main_role_id)
    new_main_nick = (await session.execute(p_stmt)).scalars().first()
    
    if not new_main_nick:
        raise HTTPException(status_code=404, detail="Player not found")
        
    # Get user who owns this character
    c_stmt = select(Character).where(func.lower(func.trim(Character.nickname)) == func.lower(func.trim(new_main_nick)))
    char_obj = (await session.execute(c_stmt)).scalars().first()
    if not char_obj:
        raise HTTPException(status_code=404, detail="Character link not found")
        
    target_user_id = char_obj.user_id
    
    # Set all chars of this user to is_main=False
    await session.execute(
        update(Character).where(Character.user_id == target_user_id).values(is_main=False)
    )
    # Set this one to is_main=True
    char_obj.is_main = True
    
    # Sync Player table is_alt
    # Reset all players of this user to is_alt=True
    stmt_p_reset = update(Player).where(Player.user_id == target_user_id).values(is_alt=True)
    await session.execute(stmt_p_reset)
    
    # Set the new main player to is_alt=False
    stmt_p_set = update(Player).where(Player.role_id == req.new_main_role_id).values(is_alt=False)
    await session.execute(stmt_p_set)
    
    await session.commit()
    return {"status": "ok", "message": "Main character updated"}


# --- Admin Settings & Backups ---

@router.get("/admin/settings", response_model=AdminSettings)
async def get_admin_settings(request: Request, session: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user or not user.is_master:
        raise HTTPException(status_code=403, detail="Permission denied")

    from database import get_setting
    
    enabled = await get_setting(session, "public_log_enabled", "false")
    chan_id = await get_setting(session, "public_log_channel_id", "")
    thread_id = await get_setting(session, "public_log_thread_id", "")
    code = await get_setting(session, "verification_code", "")

    return AdminSettings(
        public_log_enabled=(enabled == "true"),
        public_log_channel_id=chan_id,
        public_log_thread_id=thread_id,
        verification_code=code
    )

@router.post("/admin/settings")
async def update_admin_settings(request: Request, settings: AdminSettings, session: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user or not user.is_master:
        raise HTTPException(status_code=403, detail="Permission denied")

    from database import set_setting
    
    await set_setting(session, "public_log_enabled", "true" if settings.public_log_enabled else "false")
    await set_setting(session, "public_log_channel_id", settings.public_log_channel_id)
    await set_setting(session, "public_log_thread_id", settings.public_log_thread_id)
    await set_setting(session, "verification_code", settings.verification_code)

    return {"status": "ok"}

@router.get("/admin/backups", response_model=List[BackupFile])
async def list_backups(request: Request):
    user = await get_current_user(request)
    if not user or not user.is_master:
        raise HTTPException(status_code=403, detail="Permission denied")

    import glob
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
    if not os.path.exists(backup_dir):
        return []

    files = glob.glob(os.path.join(backup_dir, "guild_bot_*.*"))
    files = [f for f in files if f.endswith(".db") or f.endswith(".sql") or f.endswith(".bak")]
    files.sort(key=os.path.getmtime, reverse=True)

    result = []
    for f in files:
        result.append(BackupFile(
            name=os.path.basename(f),
            size_mb=os.path.getsize(f) / (1024 * 1024),
            mtime=os.path.getmtime(f)
        ))
    return result

@router.post("/admin/backups/create")
async def create_backup_endpoint(request: Request):
    user = await get_current_user(request)
    if not user or not user.is_master:
        raise HTTPException(status_code=403, detail="Permission denied")

    from scripts.backup_db import perform_backup
    success = perform_backup("manual_web")
    if not success:
        raise HTTPException(status_code=500, detail="Backup failed")
    return {"status": "ok"}

@router.delete("/admin/backups/{filename}")
async def delete_backup_endpoint(filename: str, request: Request):
    user = await get_current_user(request)
    if not user or not user.is_master:
        raise HTTPException(status_code=403, detail="Permission denied")

    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
    filepath = os.path.join(backup_dir, filename)
    
    if os.path.exists(filepath) and os.path.isfile(filepath):
        os.remove(filepath)
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="File not found")

@router.get("/admin/backups/download/{filename}")
async def download_backup_endpoint(filename: str, request: Request):
    user = await get_current_user(request)
    if not user or not user.is_master:
        raise HTTPException(status_code=403, detail="Permission denied")

    from fastapi.responses import FileResponse
    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
    filepath = os.path.join(backup_dir, filename)
    
    if os.path.exists(filepath) and os.path.isfile(filepath):
        return FileResponse(filepath, filename=filename)
    raise HTTPException(status_code=404, detail="File not found")

@router.post("/admin/backups/restore/{filename}")
async def restore_backup_endpoint(filename: str, request: Request):
    user = await get_current_user(request)
    if not user or not user.is_master:
        raise HTTPException(status_code=403, detail="Permission denied")

    backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backups")
    filepath = os.path.join(backup_dir, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        from scripts.restore_db import restore as restore_db_func
        # This will restart the bot process if it uses os.execv internally, 
        # but in web context it might just kill the worker. 
        # Usually web app should be restarted by system supervisor (PM2/Docker).
        # We'll call the restore script.
        restore_db_func(filepath, skip_confirm=True)
        return {"status": "ok", "message": "Restore successful. Bot is restarting..."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")

# --- FAQ / AI MANAGEMENT ---

@router.get("/admin/faq", response_model=List[FaqTopicResponse])
async def list_faq_topics(request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user or not user.is_master:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    from database import FaqTopic, FaqMessage
    from sqlalchemy import func
    
    # Get topics with message count
    stmt = select(
        FaqTopic, 
        func.count(FaqMessage.id).label("msg_count")
    ).outerjoin(FaqMessage).group_by(FaqTopic.id).order_by(FaqTopic.updated_at.desc())
    
    result = await db.execute(stmt)
    rows = result.all()
    
    res = []
    for topic, count in rows:
        res.append(FaqTopicResponse(
            id=topic.id,
            topic=topic.topic,
            content=topic.content,
            updated_at=topic.updated_at,
            message_count=count
        ))
    return res

@router.post("/admin/faq", response_model=FaqTopicResponse)
async def create_faq_topic(topic_data: FaqTopicCreate, request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user or not user.is_master:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    from database import FaqTopic, FaqMessage
    
    new_topic = FaqTopic(
        topic=topic_data.topic,
        created_by=user.telegram_id
    )
    db.add(new_topic)
    await db.flush()
    
    for i, msg in enumerate(topic_data.initial_messages):
        new_msg = FaqMessage(
            topic_id=new_topic.id,
            text=msg.text,
            photo_id=msg.photo_id,
            order_index=i
        )
        db.add(new_msg)
    
    await db.commit()
    await db.refresh(new_topic)
    
    # Trigger embedding update
    await update_topic_embedding(new_topic.id, db)
    
    return FaqTopicResponse(
        id=new_topic.id,
        topic=new_topic.topic,
        content=new_topic.content,
        updated_at=new_topic.updated_at,
        message_count=len(topic_data.initial_messages)
    )

@router.get("/admin/faq/{topic_id}")
async def get_faq_topic(topic_id: int, request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user or not user.is_master:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    from database import FaqTopic, FaqMessage
    topic = await db.get(FaqTopic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    stmt = select(FaqMessage).filter_by(topic_id=topic_id).order_by(FaqMessage.order_index)
    result = await db.execute(stmt)
    messages = result.scalars().all()
    
    return {
        "topic": FaqTopicResponse(
            id=topic.id,
            topic=topic.topic,
            content=topic.content,
            updated_at=topic.updated_at,
            message_count=len(messages)
        ),
        "messages": [FaqMessageResponse(
            id=m.id,
            topic_id=m.topic_id,
            text=m.text,
            photo_id=m.photo_id,
            order_index=m.order_index
        ) for m in messages]
    }

@router.put("/admin/faq/{topic_id}")
async def update_faq_topic(topic_id: int, topic_data: FaqTopicBase, request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user or not user.is_master:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    from database import FaqTopic, get_msk_now
    topic = await db.get(FaqTopic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    topic.topic = topic_data.topic
    topic.updated_at = get_msk_now()
    await db.commit()
    
    # Update embedding
    await update_topic_embedding(topic_id, db)
    
    return {"status": "ok"}

@router.delete("/admin/faq/{topic_id}")
async def delete_faq_topic(topic_id: int, request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user or not user.is_master:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    from database import FaqTopic
    topic = await db.get(FaqTopic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    await db.delete(topic)
    await db.commit()
    return {"status": "ok"}

@router.post("/admin/faq/{topic_id}/messages")
async def add_faq_message(topic_id: int, msg_data: FaqMessageBase, request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user or not user.is_master:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    from database import FaqTopic, FaqMessage, get_msk_now
    topic = await db.get(FaqTopic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    
    # Get max order_index
    stmt = select(func.max(FaqMessage.order_index)).filter_by(topic_id=topic_id)
    result = await db.execute(stmt)
    max_idx = result.scalar() or -1
    
    new_msg = FaqMessage(
        topic_id=topic_id,
        text=msg_data.text,
        photo_id=msg_data.photo_id,
        order_index=max_idx + 1
    )
    db.add(new_msg)
    topic.updated_at = get_msk_now()
    await db.commit()
    
    # Update embedding
    await update_topic_embedding(topic_id, db)
    
    return {"status": "ok"}

@router.delete("/admin/faq/messages/{message_id}")
async def delete_faq_message(message_id: int, request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user or not user.is_master:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    from database import FaqMessage, FaqTopic, get_msk_now
    msg = await db.get(FaqMessage, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    
    tid = msg.topic_id
    await db.delete(msg)
    
    topic = await db.get(FaqTopic, tid)
    if topic:
        topic.updated_at = get_msk_now()
        
    await db.commit()
    
    # Update embedding
    await update_topic_embedding(tid, db)
    
    return {"status": "ok"}

async def update_topic_embedding(topic_id: int, db: AsyncSession):
    """Internal helper to recompute and save embeddings for a topic."""
    from database import FaqTopic, FaqMessage
    topic = await db.get(FaqTopic, topic_id)
    if not topic:
        return
    
    stmt = select(FaqMessage).filter_by(topic_id=topic_id).order_by(FaqMessage.order_index)
    result = await db.execute(stmt)
    messages = result.scalars().all()
    
    # Prepare text for embedding
    full_text = f"Topic: {topic.topic}\n"
    for m in messages:
        if m.text:
            full_text += m.text + "\n"
        if m.photo_id:
            full_text += "[Photo]\n"
    
    from logic.ai_helper import get_ai_helper
    ai = get_ai_helper()
    if ai:
        embedding = await ai.embed_text(full_text)
        if embedding:
            import json
            topic.embedding = json.dumps(embedding)
            await db.commit()
@router.post("/admin/faq/ask")
async def ask_faq_ai(data: dict, request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user or not user.is_master:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    question = data.get("question", "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Empty question")
    
    from logic.ai_helper import get_ai_helper
    from database import FaqTopic, FaqMessage
    from sqlalchemy.orm import selectinload
    
    ai = get_ai_helper()
    if not ai:
        raise HTTPException(status_code=503, detail="AI service unavailable")
    
    # RAG Search
    relevant_topics = await ai.find_relevant_topics(question, session=db)
    
    if not relevant_topics:
        # Fallback if few topics
        stmt_count = select(func.count(FaqTopic.id))
        result_count = await db.execute(stmt_count)
        if (result_count.scalar() or 0) < 20:
             stmt_topics = select(FaqTopic).options(selectinload(FaqTopic.messages))
             result_topics = await db.execute(stmt_topics)
             relevant_topics = result_topics.scalars().all()
    
    # Build context
    context_text = ""
    for t in relevant_topics:
        context_text += f"\n--- Topic: {t.topic} ---\n"
        # Accessing .messages which should be loaded by find_relevant_topics or fallback
        # If not, we might need selectinload in find_relevant_topics
        for m in t.messages:
            if m.text:
                context_text += m.text + "\n"
    
    answer = await ai.get_answer(question, context_text)
    return {"answer": answer}


@router.post("/profile/{role_id}/set_main")
async def set_main_char(role_id: int, req: SetMainRequest, request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    from database import Player, Character
    
    # 1. Auth check: must own both role_id and req.new_main_role_id
    p = await db.get(Player, role_id)
    if not p: raise HTTPException(404)
    
    is_owner = (p.user_id == user.id)
    if not is_owner and p.nickname:
        # Fallback check character ownership via bot's characters table
        stmt_c = select(Character).where(func.lower(func.trim(Character.nickname)) == func.lower(func.trim(p.nickname)), Character.user_id == user.id)
        res_c = await db.execute(stmt_c)
        if res_c.first(): is_owner = True
        
    if not is_owner: raise HTTPException(403)
    
    new_p = await db.get(Player, req.new_main_role_id)
    if not new_p: raise HTTPException(404)
    
    is_new_owner = (new_p.user_id == user.id)
    if not is_new_owner and new_p.nickname:
        stmt_cn = select(Character).where(func.lower(func.trim(Character.nickname)) == func.lower(func.trim(new_p.nickname)), Character.user_id == user.id)
        res_cn = await db.execute(stmt_cn)
        if res_cn.first(): is_new_owner = True
        
    if not is_new_owner: raise HTTPException(403)
    
    # 2. Update Players table (Dashboard)
    stmt_all_p = select(Player).where(Player.user_id == user.id)
    res_all_p = await db.execute(stmt_all_p)
    all_p = res_all_p.scalars().all()
    
    updated_role_ids = set()
    for pl in all_p:
        pl.is_alt = (pl.role_id != req.new_main_role_id)
        updated_role_ids.add(pl.role_id)
    
    if p.role_id not in updated_role_ids:
        p.is_alt = (p.role_id != req.new_main_role_id)
        p.user_id = user.id
    if new_p.role_id not in updated_role_ids:
        new_p.is_alt = (new_p.role_id != req.new_main_role_id)
        new_p.user_id = user.id

    # 3. Synchronize Character table (Bot/Queues)
    stmt_chars = select(Character).where(Character.user_id == user.id)
    res_chars = await db.execute(stmt_chars)
    all_chars = res_chars.scalars().all()
    
    target_nick = new_p.nickname.strip().lower() if new_p.nickname else ""
    for ch in all_chars:
        ch_nick = ch.nickname.strip().lower() if ch.nickname else ""
        ch.is_main = (ch_nick == target_nick)
        
    await db.commit()
    return {"status": "ok"}

@router.get("/party/list")
async def get_all_parties(request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    from database import ConstantParty, PartyMember, Player
    stmt = select(ConstantParty).options(selectinload(ConstantParty.members))
    res = await db.execute(stmt)
    parties = res.scalars().all()
    out = []
    for p in parties:
        leader = next((m for m in p.members if m.is_leader), None)
        leader_nick = None
        if leader:
            lp = await db.get(Player, leader.player_role_id)
            if lp: leader_nick = lp.nickname
        out.append({"id": p.id, "name": p.name, "leader_nickname": leader_nick, "member_count": len(p.members)})
    return {"parties": out}

@router.post("/party/apply")
async def apply_to_party(req: CPApplicationRequest, request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    from database import Player, PartyApplication, PartyMember
    stmt = select(Player).filter_by(user_id=user.id, is_alt=False)
    p = (await db.execute(stmt)).scalars().first()
    if not p: raise HTTPException(400, detail="Main character not found")
    
    pm_stmt = select(PartyMember).filter_by(player_role_id=p.role_id)
    if (await db.execute(pm_stmt)).scalars().first():
         raise HTTPException(400, detail="Already in a party")
    
    app_stmt = select(PartyApplication).filter_by(party_id=req.party_id, player_role_id=p.role_id, status="pending")
    if (await db.execute(app_stmt)).scalars().first():
         raise HTTPException(400, detail="Already applied")
         
    new_app = PartyApplication(party_id=req.party_id, player_role_id=p.role_id, status="pending")
    db.add(new_app)
    await db.commit()
    return {"status": "ok"}

@router.get("/party/{party_id}/applications")
async def get_party_applications(party_id: int, request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    from database import PartyMember, PartyApplication, Player
    main_stmt = select(Player).filter_by(user_id=user.id, is_alt=False)
    p = (await db.execute(main_stmt)).scalars().first()
    if not p: raise HTTPException(403)
    pm = (await db.execute(select(PartyMember).filter_by(party_id=party_id, player_role_id=p.role_id, is_leader=True))).scalars().first()
    if not pm: raise HTTPException(403, detail="Not leader of this party")
    
    apps_stmt = select(PartyApplication).filter_by(party_id=party_id, status="pending")
    apps = (await db.execute(apps_stmt)).scalars().all()
    out = []
    for a in apps:
        ap = await db.get(Player, a.player_role_id)
        if ap:
            out.append({
                "application_id": a.id,
                "applicant_role_id": a.player_role_id,
                "applicant_nickname": ap.nickname,
                "applicant_class_id": ap.class_id,
                "created_at": a.created_at.isoformat() if a.created_at else ""
            })
    return {"applications": out}

@router.post("/party/applications/resolve")
async def resolve_party_application(req: CPResolveRequest, request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    from database import PartyMember, PartyApplication, Player
    main_stmt = select(Player).filter_by(user_id=user.id, is_alt=False)
    p = (await db.execute(main_stmt)).scalars().first()
    if not p: raise HTTPException(403)
    
    app = await db.get(PartyApplication, req.application_id)
    if not app or app.status != "pending": raise HTTPException(404, detail="Application not found or already resolved")
    
    pm = (await db.execute(select(PartyMember).filter_by(party_id=app.party_id, player_role_id=p.role_id, is_leader=True))).scalars().first()
    if not pm: raise HTTPException(403, detail="Not leader")
    
    app.status = req.action
    if req.action == "accept":
        epm = (await db.execute(select(PartyMember).filter_by(player_role_id=app.player_role_id))).scalars().first()
        if not epm:
            new_member = PartyMember(party_id=app.party_id, player_role_id=app.player_role_id, is_leader=False)
            db.add(new_member)
    await db.commit()
    return {"status": "ok"}

@router.post("/party/create_named")
async def create_party_named(req: CPCreateRequest, request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    from database import ConstantParty, PartyMember, Player
    main_stmt = select(Player).filter_by(user_id=user.id, is_alt=False)
    p = (await db.execute(main_stmt)).scalars().first()
    if not p: raise HTTPException(400, detail="Main char not found")
    
    if (await db.execute(select(PartyMember).filter_by(player_role_id=p.role_id))).scalars().first():
         raise HTTPException(400, detail="Already in a party")
         
    new_party = ConstantParty(name=req.name)
    db.add(new_party)
    await db.flush() 
    new_member = PartyMember(party_id=new_party.id, player_role_id=p.role_id, is_leader=True)
    db.add(new_member)
    await db.commit()
    return {"status": "ok", "party_id": new_party.id}

@router.post("/party/add_member")
async def add_party_member(req: CPAddMemberRequest, request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    from database import PartyMember, Player
    # 1. Verify requester is leader
    main_stmt = select(Player).filter_by(user_id=user.id, is_alt=False)
    p = (await db.execute(main_stmt)).scalars().first()
    if not p: raise HTTPException(403)
    pm = (await db.execute(select(PartyMember).filter_by(party_id=req.party_id, player_role_id=p.role_id, is_leader=True))).scalars().first()
    if not pm: raise HTTPException(403, detail="Not leader of this party")
    
    # 2. Find target player by nickname
    target_p = (await db.execute(select(Player).filter_by(nickname=req.nickname))).scalars().first()
    if not target_p: raise HTTPException(404, detail="Player not found")
    
    # 3. Check if already in party
    existing = (await db.execute(select(PartyMember).filter_by(player_role_id=target_p.role_id))).scalars().first()
    if existing:
         raise HTTPException(400, detail="Player already in a party")
         
    # 4. Add to party
    new_member = PartyMember(party_id=req.party_id, player_role_id=target_p.role_id, is_leader=False)
    db.add(new_member)
    await db.commit()
    return {"status": "ok"}

@router.get("/party/{role_id}/kh_stats", response_model=SquadKHStatsResponse)
async def get_party_kh_stats(role_id: int, period: str = Query("day"), offset: int = Query(0), request: Request = None, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    from database import Player, PartyMember
    pm_stmt = select(PartyMember).filter_by(player_role_id=role_id)
    pm = (await db.execute(pm_stmt)).scalars().first()
    if not pm:
         raise HTTPException(status_code=404, detail="Party not found")
         
    party_id = pm.party_id
    all_members = (await db.execute(select(PartyMember).filter_by(party_id=party_id))).scalars().all()
    member_role_ids = [m.player_role_id for m in all_members]
    
    from logic.player_manager import calculate_calendar_stats
    squad_stats = []
    start_date = ""
    end_date = ""
    for r_id in member_role_ids:
        pl = await db.get(Player, r_id)
        if pl:
            stats = await calculate_calendar_stats(db, r_id, period, offset)
            squad_stats.append({
                "role_id": r_id,
                "nickname": pl.nickname,
                "stats": stats["stats"]
            })
            if not start_date:
                start_date = stats["start_date"]
                end_date = stats["end_date"]
                
    return {
        "period": period,
        "offset": offset,
        "start_date": start_date or "",
        "end_date": end_date or "",
        "squad_stats": squad_stats
    }

class CPKickRequest(BaseModel):
    party_id: int
    role_id: int

class CPTransferRequest(BaseModel):
    party_id: int
    new_leader_role_id: int

@router.post("/party/kick")
async def kick_party_member_endpoint(req: CPKickRequest, request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    from database import PartyMember, Player
    
    # 1. Verify requester is leader of the party or Master
    main_stmt = select(Player).filter_by(user_id=user.id, is_alt=False)
    p = (await db.execute(main_stmt)).scalars().first()
    
    can_kick = user.is_master
    if not can_kick and p:
        pm_leader = (await db.execute(select(PartyMember).filter_by(party_id=req.party_id, player_role_id=p.role_id, is_leader=True))).scalars().first()
        if pm_leader: can_kick = True
        
    if not can_kick: raise HTTPException(403, detail="Permission denied")
    
    # 2. Delete member record
    target_pm = (await db.execute(select(PartyMember).filter_by(party_id=req.party_id, player_role_id=req.role_id))).scalars().first()
    if target_pm:
        if target_pm.is_leader and not user.is_master:
             raise HTTPException(400, detail="Cannot kick a leader")
        await db.delete(target_pm)
        await db.commit()
    return {"status": "ok"}

@router.post("/party/transfer_leadership")
async def transfer_party_leadership_endpoint(req: CPTransferRequest, request: Request, db: AsyncSession = Depends(get_session)):
    user = await get_current_user(request)
    if not user: raise HTTPException(401)
    from database import PartyMember, Player
    
    # 1. Verify requester is current leader
    main_stmt = select(Player).filter_by(user_id=user.id, is_alt=False)
    p = (await db.execute(main_stmt)).scalars().first()
    if not p and not user.is_master: raise HTTPException(403)
    
    pm_leader = None
    if not user.is_master:
        pm_leader = (await db.execute(select(PartyMember).filter_by(party_id=req.party_id, player_role_id=p.role_id, is_leader=True))).scalars().first()
        if not pm_leader: raise HTTPException(403, detail="Not a leader")
    else:
        # Master can transfer leadership for any party
        pm_leader = (await db.execute(select(PartyMember).filter_by(party_id=req.party_id, is_leader=True))).scalars().first()

    # 2. Find new leader record
    new_leader_pm = (await db.execute(select(PartyMember).filter_by(party_id=req.party_id, player_role_id=req.new_leader_role_id))).scalars().first()
    if not new_leader_pm: raise HTTPException(404, detail="Target player not in party")
    
    if pm_leader:
        pm_leader.is_leader = False
    new_leader_pm.is_leader = True
    await db.commit()
    return {"status": "ok"}

