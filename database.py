import os
from datetime import datetime
from typing import Optional

import pytz
from dotenv import load_dotenv
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, select, update, delete, BigInteger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship, selectinload

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://guild_user:your_password@localhost/guild_bot")

# Timezone Helper
MSK = pytz.timezone("Europe/Moscow")


def get_msk_now():
    """Returns current time in MSK as naive datetime"""
    return datetime.now(MSK).replace(tzinfo=None)


Base = declarative_base()
session = None # Placeholder for legacy synchronous tests to patch

# --- МОДЕЛИ ---


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True)
    username = Column(String)
    avatar_url = Column(String, nullable=True)
    pending_request_nick = Column(String, nullable=True)  # For unauthorized users waiting approval
    is_master = Column(Boolean, default=False)
    is_banned = Column(Boolean, default=False)
    personal_limit = Column(Integer, nullable=True)
    afk_start = Column(DateTime, nullable=True)
    afk_end = Column(DateTime, nullable=True)
    afk_reason = Column(String, nullable=True)
    characters = relationship("Character", back_populates="user", cascade="all, delete-orphan")


class Settings(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True)
    value = Column(String)


class Character(Base):
    __tablename__ = "characters"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    nickname = Column(String)
    is_main = Column(Boolean, default=False)
    user = relationship("User", back_populates="characters")


class QueueType(Base):
    __tablename__ = "queue_types"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    description = Column(String, default="Стандартные условия")
    is_active = Column(Boolean, default=True)
    is_locked = Column(Boolean, default=False)


class QueueEntry(Base):
    __tablename__ = "queue_entries"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    queue_type_id = Column(Integer, ForeignKey("queue_types.id"))
    character_name = Column(String, index=True)
    auto_requeue = Column(Boolean, default=False)
    position = Column(Integer, default=0)
    user = relationship("User")
    queue = relationship("QueueType")


class RewardHistory(Base):
    __tablename__ = "reward_history"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    character_name = Column(String)
    queue_name = Column(String)
    issued_by = Column(String)
    is_notified = Column(Boolean, default=True)  # Default True for old records/backwards compat if immediately sent
    record_type = Column(String, default="reward")  # "reward" or "warning"
    timestamp = Column(DateTime, default=get_msk_now)


class ScheduledAnnouncement(Base):
    __tablename__ = "announcements"
    id = Column(Integer, primary_key=True)
    text = Column(String)
    schedule_type = Column(String)
    run_time = Column(String)
    days_of_week = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)


class Player(Base):
    __tablename__ = "players"
    role_id = Column(Integer, primary_key=True)
    nickname = Column(String, default=None, index=True)
    first_seen = Column(DateTime, default=get_msk_now)
    in_clan = Column(Integer, default=1)
    class_id = Column(Integer, default=-1)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_alt = Column(Boolean, default=False)
    afk_start = Column(DateTime, nullable=True)
    afk_end = Column(DateTime, nullable=True)
    afk_reason = Column(String, nullable=True)
    # Relationship to user
    user = relationship("User", backref="game_characters")


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    role_id = Column(Integer, index=True)
    timestamp = Column(Integer)
    event_date = Column(String, index=True)
    event_type = Column(Integer, index=True)
    value = Column(Integer)
    raw_desc = Column(String)


class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    icon_url = Column(String, nullable=True)


class AFKHistory(Base):
    __tablename__ = "afk_history"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    role_id = Column(Integer, nullable=True)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    is_active_record = Column(Boolean, default=True)  # True if this was a finalized period
    reason = Column(String, nullable=True)
    timestamp = Column(DateTime, default=get_msk_now)
    # Relationship
    user = relationship("User", backref="afk_history")



class ObserverCache(Base):
    __tablename__ = "observer_cache"
    role_id = Column(Integer, primary_key=True)
    html_content = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow)


# КП (Constant Party) - группы для постоянной игры вместе
class ConstantParty(Base):
    __tablename__ = "constant_parties"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=True)  # Опциональное название
    color = Column(String, nullable=True) # Цвет неона (HEX/RGB)
    created_at = Column(DateTime, default=get_msk_now)
    members = relationship("PartyMember", back_populates="party", cascade="all, delete-orphan")


class PartyMember(Base):
    __tablename__ = "party_members"
    id = Column(Integer, primary_key=True)
    party_id = Column(Integer, ForeignKey("constant_parties.id"))
    player_role_id = Column(Integer)  # role_id из players
    is_leader = Column(Boolean, default=False)  # Лидер может управлять пати
    party = relationship("ConstantParty", back_populates="members")


class FaqTopic(Base):
    __tablename__ = "faq_topics"
    id = Column(Integer, primary_key=True)
    topic = Column(String)
    content = Column(String)
    created_by = Column(BigInteger)  # User ID of creator (Telegram ID)
    updated_at = Column(DateTime, default=get_msk_now)
    # RAG Support
    embedding = Column(String, nullable=True)  # JSON-serialized list of floats
    
    messages = relationship("FaqMessage", back_populates="topic", cascade="all, delete-orphan")


class FaqMessage(Base):
    __tablename__ = "faq_messages"
    id = Column(Integer, primary_key=True)
    topic_id = Column(Integer, ForeignKey("faq_topics.id"))
    text = Column(String, nullable=True)
    photo_id = Column(String, nullable=True)  # Telegram File ID
    order_index = Column(Integer, default=0)
    
    topic = relationship("FaqTopic", back_populates="messages")


class MessageLog(Base):
    __tablename__ = "message_logs"
    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger)  # BigInteger in real DB, Integer in SQLite is dynamic
    thread_id = Column(Integer, nullable=True)
    user_id = Column(BigInteger)
    user_name = Column(String)
    text = Column(String)
    timestamp = Column(DateTime, default=get_msk_now)


class SummaryState(Base):
    __tablename__ = "summary_states"
    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger)
    thread_id = Column(Integer, nullable=True)
    last_summary_time = Column(DateTime)




# --- ИНИЦИАЛИЗАЦИЯ ---

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

DEFAULT_QUEUES = [
    "Жемчужины Фу Си",
    "Знаки Единства",
    "Колода карт",
    "Сущность карты",
    "Камень божества",
    "Драконья чешуя",
    "Цилинь",
]


async def init_db():
    """Инициализация БД (теперь через Alembic, но оставим для тестов/первичного запуска)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Инициализация дефолтных значений
    async with AsyncSessionLocal() as session:
        for q_name in DEFAULT_QUEUES:
            result = await session.execute(select(QueueType).filter_by(name=q_name))
            if not result.scalar_one_or_none():
                session.add(QueueType(name=q_name))

        result = await session.execute(select(Settings).filter_by(key="default_limit"))
        if not result.scalar_one_or_none():
            session.add(Settings(key="default_limit", value="1"))

        await session.commit()


# --- ФУНКЦИИ ЗАПРОСОВ (Refactored to be generic or internal) ---


async def ensure_user(session: AsyncSession, telegram_id: int, username: Optional[str]):
    """Получает или создает пользователя."""
    result = await session.execute(
        select(User).filter_by(telegram_id=telegram_id).options(selectinload(User.characters))
    )
    user = result.scalar_one_or_none()
    
    if not user and username:
        result = await session.execute(
            select(User)
            .filter(User.username.ilike(username))
            .filter(User.telegram_id.is_(None))
            .options(selectinload(User.characters))
        )
        user = result.scalar_one_or_none()
        if user:
            user.telegram_id = telegram_id
            await session.commit()

    if not user:
        result = await session.execute(select(User))
        is_first = len(result.all()) == 0
        user = User(telegram_id=telegram_id, username=username, is_master=is_first)
        session.add(user)
        await session.commit()
        
    return user


async def get_user_active_queues(session: AsyncSession, user_id: int):
    """Возвращает список активных записей пользователя."""
    result = await session.execute(select(QueueEntry).filter_by(user_id=user_id))
    return result.scalars().all()


async def get_effective_limit_logic(session: AsyncSession, user: User):
    """Считает актуальный лимит для юзера (Личный или Общий)."""
    if user.personal_limit is not None:
        return user.personal_limit

    result = await session.execute(select(Settings).filter_by(key="default_limit"))
    setting = result.scalar_one_or_none()
    return int(setting.value) if setting else 1


async def get_setting(session: AsyncSession, key: str, default=None):
    result = await session.execute(select(Settings).filter_by(key=key))
    s = result.scalar_one_or_none()
    return s.value if s else default


async def set_setting(session: AsyncSession, key: str, value):
    result = await session.execute(select(Settings).filter_by(key=key))
    s = result.scalar_one_or_none()
    if not s:
        s = Settings(key=key)
        session.add(s)
    s.value = str(value)
    await session.commit()
