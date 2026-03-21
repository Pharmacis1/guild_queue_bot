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
