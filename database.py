from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import pytz

# Timezone Helper
MSK = pytz.timezone('Europe/Moscow')

def get_msk_now():
    """Returns current time in MSK as naive datetime (for SQLite compatibility)"""
    return datetime.now(MSK).replace(tzinfo=None) # Make naive so SQLite doesn't complain

Base = declarative_base()

# --- МОДЕЛИ ---

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String)
    avatar_url = Column(String, nullable=True)
    pending_request_nick = Column(String, nullable=True) # For unauthorized users waiting approval
    is_master = Column(Boolean, default=False)
    is_banned = Column(Boolean, default=False)
    personal_limit = Column(Integer, nullable=True) 
    afk_start = Column(DateTime, nullable=True)
    afk_end = Column(DateTime, nullable=True)
    characters = relationship("Character", back_populates="user", cascade="all, delete-orphan")

class Settings(Base):
    __tablename__ = 'settings'
    key = Column(String, primary_key=True)
    value = Column(String)

class Character(Base):
    __tablename__ = 'characters'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    nickname = Column(String)
    is_main = Column(Boolean, default=False)
    user = relationship("User", back_populates="characters")

class QueueType(Base):
    __tablename__ = 'queue_types'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    description = Column(String, default="Стандартные условия")
    is_active = Column(Boolean, default=True)
    is_locked = Column(Boolean, default=False)
    
class QueueEntry(Base):
    __tablename__ = 'queue_entries'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    queue_type_id = Column(Integer, ForeignKey('queue_types.id'))
    character_name = Column(String)
    auto_requeue = Column(Boolean, default=False)
    user = relationship("User")
    queue = relationship("QueueType")

class RewardHistory(Base):
    __tablename__ = 'reward_history'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    character_name = Column(String)
    queue_name = Column(String)
    issued_by = Column(String)
    is_notified = Column(Boolean, default=True) # Default True for old records/backwards compat if immediately sent
    record_type = Column(String, default="reward") # "reward" or "warning"
    timestamp = Column(DateTime, default=get_msk_now)

class ScheduledAnnouncement(Base):
    __tablename__ = 'announcements'
    id = Column(Integer, primary_key=True)
    text = Column(String)
    schedule_type = Column(String)
    run_time = Column(String)
    days_of_week = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

class Player(Base):
    __tablename__ = 'players'
    role_id = Column(Integer, primary_key=True)
    nickname = Column(String, default=None)
    first_seen = Column(DateTime, default=get_msk_now)
    in_clan = Column(Integer, default=1)
    class_id = Column(Integer, default=-1)

class Event(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True)
    role_id = Column(Integer)
    timestamp = Column(Integer)
    event_date = Column(String)
    event_type = Column(Integer)
    value = Column(Integer)
    raw_desc = Column(String)

class Item(Base):
    __tablename__ = 'items'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    icon_url = Column(String, nullable=True)

class AFKHistory(Base):
    __tablename__ = 'afk_history'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    is_active_record = Column(Boolean, default=True) # True if this was a finalized period

class ObserverCache(Base):
    __tablename__ = 'observer_cache'
    role_id = Column(Integer, primary_key=True)
    html_content = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow)


# --- ИНИЦИАЛИЗАЦИЯ ---

engine = create_engine('sqlite:///guild_bot.db', echo=False)
Session = sessionmaker(bind=engine)
session = Session()

def init_db():
    Base.metadata.create_all(engine)
    
    # --- AUTO MIGRATION (Pending Nick & AFK) ---
    with engine.connect() as conn:
        from sqlalchemy import text
        
        # 1. Pending Request Nick
        try:
            conn.execute(text("SELECT pending_request_nick FROM users LIMIT 1"))
        except:
            print("Column 'pending_request_nick' missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN pending_request_nick VARCHAR"))
                print("Migration successful: Added pending_request_nick")
            except Exception as e:
                print(f"Migration failed (pending_request_nick): {e}")

        # 2. AFK Columns
        try:
            conn.execute(text("SELECT afk_start FROM users LIMIT 1"))
        except:
            print("Column 'afk_start' missing. Migrating...")
            try:
                # SQLite usually allows only one ADD COLUMN per statement, so we do two
                conn.execute(text("ALTER TABLE users ADD COLUMN afk_start DATETIME"))
                conn.execute(text("ALTER TABLE users ADD COLUMN afk_end DATETIME"))
                print("Migration successful: Added afk_start/end")
            except Exception as e:
                print(f"Migration failed (afk): {e}")
    # -------------------------------------

        try:
            conn.execute(text("SELECT auto_requeue FROM queue_entries LIMIT 1"))
        except:
            print("Column 'auto_requeue' missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE queue_entries ADD COLUMN auto_requeue BOOLEAN DEFAULT 0"))
                print("Migration successful: Added auto_requeue")
            except Exception as e:
                print(f"Migration failed (auto_requeue): {e}")

        # 4. RewardHistory Is Notified
        try:
            conn.execute(text("SELECT is_notified FROM reward_history LIMIT 1"))
        except:
            print("Column 'is_notified' missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE reward_history ADD COLUMN is_notified BOOLEAN DEFAULT 1"))
                print("Migration successful: Added is_notified")
            except Exception as e:
                print(f"Migration failed (is_notified): {e}")

        # 5. RewardHistory Record Type
        try:
            conn.execute(text("SELECT record_type FROM reward_history LIMIT 1"))
        except:
            print("Column 'record_type' missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE reward_history ADD COLUMN record_type VARCHAR DEFAULT 'reward'"))
                print("Migration successful: Added record_type")
            except Exception as e:
                print(f"Migration failed (record_type): {e}")
    
    queues = [
        "Камень доблести", "Метеориты", "Жемчужины Фу Си", "Опыт в диск",
        "Проходки в УФ", "Знаки Единства", "Колода карт", "Сущность карты",
        "Камень божества", "Камни бессмертных", "Цилинь"
    ]
    for q_name in queues:
        if not session.query(QueueType).filter_by(name=q_name).first():
            session.add(QueueType(name=q_name))
            
    if not session.query(Settings).filter_by(key="default_limit").first():
        session.add(Settings(key="default_limit", value="1"))
        
    session.commit()

# --- ФУНКЦИИ ЗАПРОСОВ (Перенесли сюда) ---

def ensure_user(telegram_id, username):
    """Получает или создает пользователя."""
    user = session.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        is_first = session.query(User).count() == 0
        user = User(telegram_id=telegram_id, username=username, is_master=is_first)
        session.add(user)
        session.commit()
    return user

def get_user_active_queues(user_id):
    """Возвращает список активных записей пользователя."""
    return session.query(QueueEntry).filter_by(user_id=user_id).all()


def get_effective_limit_logic(user):
    """Считает актуальный лимит для юзера (Личный или Общий)."""
    # Если у пользователя установлен личный лимит
    if user.personal_limit is not None:
        return user.personal_limit
        
    setting = session.query(Settings).filter_by(key="default_limit").first()
    return int(setting.value) if setting else 1

def get_setting(key, default=None):
    s = session.query(Settings).filter_by(key=key).first()
    return s.value if s else default

def set_setting(key, value):
    s = session.query(Settings).filter_by(key=key).first()
    if not s:
        s = Settings(key=key)
        session.add(s)
    s.value = str(value)
    session.commit()