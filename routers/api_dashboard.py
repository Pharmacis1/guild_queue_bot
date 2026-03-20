from datetime import datetime, timedelta
from typing import List, Optional, Any
import os

from fastapi import APIRouter, Depends, Query, Request, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from consts import CLASSES
from database import User, AsyncSessionLocal, Player, get_session
from sqlalchemy.ext.asyncio import AsyncSession
from web_database import get_last_update_time
from logic.dashboard import get_kh_table_data, get_history_data, get_money_table_data

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# --- Models ---

class UserData(BaseModel):
    id: int
    telegram_id: Optional[int] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    is_master: bool
    is_banned: bool

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
    item_name: Optional[str]
    is_mine: bool
    is_afk: bool
    afk_dates: Optional[str]
    afk_reason: Optional[str] = None
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

class ProfileLinkedChar(BaseModel):
    nickname: str
    is_main: bool
    class_id: Optional[int] = 0

class ProfilePartyMember(BaseModel):
    nickname: Optional[str]
    is_leader: bool
    class_id: int
    role_id: int

class ProfileParty(BaseModel):
    id: int
    name: Optional[str]
    is_leader: bool
    members: List[ProfilePartyMember]

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


# --- Helpers ---

async def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(User).options(selectinload(User.characters)).filter_by(telegram_id=user_id)
        )
        return result.scalar_one_or_none()

# --- Endpoints ---

@router.get("/init", response_model=InitResponse)
async def get_init_data(request: Request):
    user = await get_current_user(request)
    last_upd = await get_last_update_time()
    
    # Fetch active queue types
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(text("SELECT id, name FROM queue_types WHERE is_active = TRUE"))
        queue_types = [dict(r) for r in result.mappings().all()]

    user_data = None
    if user:
        user_data = UserData(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username or "Unknown",
            avatar_url=user.avatar_url,
            is_master=user.is_master,
            is_banned=user.is_banned
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
async def get_profile_endpoint(role_id: int, session: AsyncSession = Depends(get_session)):
    # Dynamic import to avoid circular dependency if any (though logic modules usually okay)
    from logic.player_manager import get_player_profile
    data = await get_player_profile(session, role_id)
    if not data:
         # Return empty or error? Better 404 but for now valid empty struct
         # Actually let's return 404 if not found
         from fastapi import HTTPException
         raise HTTPException(status_code=404, detail="Player not found")
    
    # helper to safe convert dates
    if data.get("afk_start"): data["afk_start"] = str(data["afk_start"])
    if data.get("afk_end"): data["afk_end"] = str(data["afk_end"])

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
        player_row = player_result.scalar_one_or_none()

        if player_row:
            char_row = await session.execute(select(Character).filter_by(user_id=user.id, nickname=player_row.nickname))
            char = char_row.scalar_one_or_none()
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
