from datetime import datetime

import pytz
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# Timezone Helper
MSK = pytz.timezone("Europe/Moscow")


def get_msk_now():
    """Returns current time in MSK as naive datetime (for SQLite compatibility)"""
    return datetime.now(MSK).replace(tzinfo=None)  # Make naive so SQLite doesn't complain


Base = declarative_base()

# --- МОДЕЛИ ---


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String)
    avatar_url = Column(String, nullable=True)
    pending_request_nick = Column(String, nullable=True)  # For unauthorized users waiting approval
    is_master = Column(Boolean, default=False)
    is_banned = Column(Boolean, default=False)
    personal_limit = Column(Integer, nullable=True)
    afk_start = Column(DateTime, nullable=True)
    afk_end = Column(DateTime, nullable=True)
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
    character_name = Column(String)
    auto_requeue = Column(Boolean, default=False)
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
    nickname = Column(String, default=None)
    first_seen = Column(DateTime, default=get_msk_now)
    in_clan = Column(Integer, default=1)
    class_id = Column(Integer, default=-1)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_alt = Column(Boolean, default=False)
    # Relationship to user
    user = relationship("User", backref="game_characters")


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    role_id = Column(Integer)
    timestamp = Column(Integer)
    event_date = Column(String)
    event_type = Column(Integer)
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
    created_by = Column(Integer)  # User ID of creator (Telegram ID)
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
    chat_id = Column(Integer)  # BigInteger in real DB, Integer in SQLite is dynamic
    thread_id = Column(Integer, nullable=True)
    user_id = Column(Integer)
    user_name = Column(String)
    text = Column(String)
    timestamp = Column(DateTime, default=get_msk_now)


class SummaryState(Base):
    __tablename__ = "summary_states"
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer)
    thread_id = Column(Integer, nullable=True)
    last_summary_time = Column(DateTime)


# --- ИНИЦИАЛИЗАЦИЯ ---

engine = create_engine("sqlite:///guild_bot.db", echo=False)
Session = sessionmaker(bind=engine)
session = Session()

DEFAULT_QUEUES = [
    "Жемчужины Фу Си",
    "Знаки Единства",
    "Колода карт",
    "Сущность карты",
    "Камень божества",
    "Драконья чешуя",
    "Цилинь",
]


def init_db():
    Base.metadata.create_all(engine)

    # --- AUTO MIGRATION (Pending Nick & AFK) ---
    with engine.connect() as conn:
        from sqlalchemy import text

        # 1. Pending Request Nick
        try:
            conn.execute(text("SELECT pending_request_nick FROM users LIMIT 1"))
        except Exception:
            print("Column 'pending_request_nick' missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN pending_request_nick VARCHAR"))
                print("Migration successful: Added pending_request_nick")
            except Exception as e:
                print(f"Migration failed (pending_request_nick): {e}")

        # 2. AFK Columns
        try:
            conn.execute(text("SELECT afk_start FROM users LIMIT 1"))
        except Exception:
            print("Column 'afk_start' missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN afk_start DATETIME"))
                conn.execute(text("ALTER TABLE users ADD COLUMN afk_end DATETIME"))
                print("Migration successful: Added afk_start/end")
            except Exception as e:
                print(f"Migration failed (afk): {e}")

        # 2.1. User Avatar URL
        try:
            conn.execute(text("SELECT avatar_url FROM users LIMIT 1"))
        except Exception:
            print("Column 'avatar_url' missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN avatar_url TEXT"))
                print("Migration successful: Added avatar_url")
            except Exception as e:
                print(f"Migration failed (avatar_url): {e}")

        # 2.2. User Personal Limit
        try:
            conn.execute(text("SELECT personal_limit FROM users LIMIT 1"))
        except Exception:
            print("Column 'personal_limit' missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN personal_limit INTEGER"))
                print("Migration successful: Added personal_limit")
            except Exception as e:
                print(f"Migration failed (personal_limit): {e}")

        # -------------------------------------

        try:
            conn.execute(text("SELECT auto_requeue FROM queue_entries LIMIT 1"))
        except Exception:
            print("Column 'auto_requeue' missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE queue_entries ADD COLUMN auto_requeue BOOLEAN DEFAULT 0"))
                print("Migration successful: Added auto_requeue")
            except Exception as e:
                print(f"Migration failed (auto_requeue): {e}")

        # 4. RewardHistory Is Notified
        try:
            conn.execute(text("SELECT is_notified FROM reward_history LIMIT 1"))
        except Exception:
            print("Column 'is_notified' missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE reward_history ADD COLUMN is_notified BOOLEAN DEFAULT 1"))
                print("Migration successful: Added is_notified")
            except Exception as e:
                print(f"Migration failed (is_notified): {e}")

        try:
            conn.execute(text("SELECT record_type FROM reward_history LIMIT 1"))
        except Exception:
            print("Column 'record_type' missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE reward_history ADD COLUMN record_type VARCHAR DEFAULT 'reward'"))
                print("Migration successful: Added record_type")
            except Exception as e:
                print(f"Migration failed (record_type): {e}")

        # 5.1. RewardHistory Issued By
        try:
            conn.execute(text("SELECT issued_by FROM reward_history LIMIT 1"))
        except Exception:
            print("Column 'issued_by' missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE reward_history ADD COLUMN issued_by VARCHAR"))
                print("Migration successful: Added issued_by")
            except Exception as e:
                print(f"Migration failed (issued_by): {e}")

        # 6. Player User Link & Alt Status
        try:
            conn.execute(text("SELECT user_id FROM players LIMIT 1"))
        except Exception:
            print("Column 'user_id' in players missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE players ADD COLUMN user_id INTEGER REFERENCES users(id)"))
                print("Migration successful: Added players.user_id")
            except Exception as e:
                print(f"Migration failed (players.user_id): {e}")

        try:
            conn.execute(text("SELECT is_alt FROM players LIMIT 1"))
        except Exception:
            print("Column 'is_alt' in players missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE players ADD COLUMN is_alt BOOLEAN DEFAULT 0"))
                print("Migration successful: Added players.is_alt")
            except Exception as e:
                print(f"Migration failed (players.is_alt): {e}")

        # 7. Disable Removed Queues
        queues_to_disable = ["Камень доблести", "Метеориты", "Опыт в диск", "Проходки в УФ", "Камни бессмертных"]
        q_names_sql = "', '".join(queues_to_disable)

        # Check if any are still active
        check_sql = f"SELECT count(*) FROM queue_types WHERE name IN ('{q_names_sql}') AND is_active = 1"
        active_count = conn.execute(text(check_sql)).scalar()

        if active_count > 0:
            print(f"Found {active_count} active queues to disable. Migrating...")
            try:
                # Disable queues
                conn.execute(text(f"UPDATE queue_types SET is_active = 0 WHERE name IN ('{q_names_sql}')"))

                # Retrieve IDs of disabled queues for entry deletion
                # (SQLite doesn't support returning clause in update widely enough to rely on it via sqlalchemy text depending on version, so query first/after)
                # Actually, we can just delete via join or subquery logic, but SQLite simple DELETE is safest with subquery

                conn.execute(
                    text(
                        f"DELETE FROM queue_entries WHERE queue_type_id IN (SELECT id FROM queue_types WHERE name IN ('{q_names_sql}'))"
                    )
                )

                print("Migration successful: Disabled queues and removed entries.")
                conn.commit()
            except Exception as e:
                print(f"Migration failed (disable queues): {e}")

        # 8. AFK History Table (Ensure existence)
        try:
            conn.execute(text("SELECT count(*) FROM afk_history LIMIT 1"))
        except Exception:
            print("Table 'afk_history' missing. Migrating...")
            try:
                conn.execute(
                    text("""
                    CREATE TABLE afk_history (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER REFERENCES users(id),
                        role_id INTEGER,
                        start_date DATETIME,
                        end_date DATETIME,
                        is_active_record BOOLEAN DEFAULT 1
                    )
                """)
                )
                print("Migration successful: Created afk_history table")
            except Exception as e:
                print(f"Migration failed (afk_history table): {e}")

        # 8.1. AFK History Role ID Migration
        try:
            conn.execute(text("SELECT role_id FROM afk_history LIMIT 1"))
        except Exception:
            print("Column 'role_id' in afk_history missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE afk_history ADD COLUMN role_id INTEGER"))
                print("Migration successful: Added afk_history.role_id")
            except Exception as e:
                print(f"Migration failed (afk_history.role_id): {e}")

        # 8.2. AFK History Reason Migration
        try:
            conn.execute(text("SELECT reason FROM afk_history LIMIT 1"))
        except Exception:
            print("Column 'reason' in afk_history missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE afk_history ADD COLUMN reason VARCHAR"))
                print("Migration successful: Added afk_history.reason")
            except Exception as e:
                print(f"Migration failed (afk_history.reason): {e}")


        # 9. FAQ Topics Table (Ensure existence)
        try:
            conn.execute(text("SELECT count(*) FROM faq_topics LIMIT 1"))
        except Exception:
            print("Table 'faq_topics' missing. Migrating...")
            try:
                conn.execute(
                    text("""
                    CREATE TABLE faq_topics (
                        id INTEGER PRIMARY KEY,
                        topic VARCHAR,
                        content VARCHAR,
                        created_by INTEGER,
                        updated_at DATETIME
                    )
                """)
                )
                print("Migration successful: Created faq_topics table")
            except Exception as e:
                print(f"Migration failed (faq_topics table): {e}")

        # 10. MessageLog Table
        try:
            conn.execute(text("SELECT count(*) FROM message_logs LIMIT 1"))
        except Exception:
            print("Table 'message_logs' missing. Migrating...")
            try:
                conn.execute(
                    text("""
                    CREATE TABLE message_logs (
                        id INTEGER PRIMARY KEY,
                        chat_id INTEGER,
                        thread_id INTEGER,
                        user_id INTEGER,
                        user_name VARCHAR,
                        text VARCHAR,
                        timestamp DATETIME
                    )
                """)
                )
                print("Migration successful: Created message_logs table")
            except Exception as e:
                print(f"Migration failed (message_logs table): {e}")

        # 11. SummaryState Table
        try:
            conn.execute(text("SELECT count(*) FROM summary_states LIMIT 1"))
        except Exception:
            print("Table 'summary_states' missing. Migrating...")
            try:
                conn.execute(
                    text("""
                    CREATE TABLE summary_states (
                        id INTEGER PRIMARY KEY,
                        chat_id INTEGER,
                        thread_id INTEGER,
                        last_summary_time DATETIME
                    )
                """)
                )
                print("Migration successful: Created summary_states table")
            except Exception as e:
                print(f"Migration failed (summary_states table): {e}")

        # 12. RAG & Multi-Message Migration
        # A. Add embedding to FaqTopic
        try:
            conn.execute(text("SELECT embedding FROM faq_topics LIMIT 1"))
        except Exception:
            print("Column 'embedding' in faq_topics missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE faq_topics ADD COLUMN embedding VARCHAR"))
                print("Migration successful: Added faq_topics.embedding")
            except Exception as e:
                print(f"Migration failed (faq_topics.embedding): {e}")

        # B. Create FaqMessage table
        try:
            conn.execute(text("SELECT count(*) FROM faq_messages LIMIT 1"))
        except Exception:
            print("Table 'faq_messages' missing. Migrating...")
            try:
                conn.execute(
                    text("""
                    CREATE TABLE faq_messages (
                        id INTEGER PRIMARY KEY,
                        topic_id INTEGER REFERENCES faq_topics(id),
                        text VARCHAR,
                        photo_id VARCHAR,
                        order_index INTEGER DEFAULT 0
                    )
                """)
                )
                print("Migration successful: Created faq_messages table")
                
                # C. Data Migration: Move FaqTopic.content -> FaqMessage
                # We need to do this via session usually, but plain SQL is faster for simple move if no logic needed.
                # SQLite: INSERT INTO faq_messages (topic_id, text, order_index) SELECT id, content, 0 FROM faq_topics WHERE content IS NOT NULL
                conn.execute(
                    text("INSERT INTO faq_messages (topic_id, text, order_index) SELECT id, content, 0 FROM faq_topics WHERE content IS NOT NULL AND content != ''")
                )
                print("Data Migration: Moved existing content to messages.")
                
            except Exception as e:
                print(f"Migration failed (faq_messages table): {e}")

        # 13. Constant Party Color
        try:
            conn.execute(text("SELECT color FROM constant_parties LIMIT 1"))
        except Exception:
            print("Column 'color' in constant_parties missing. Migrating...")
            try:
                conn.execute(text("ALTER TABLE constant_parties ADD COLUMN color VARCHAR"))
                print("Migration successful: Added constant_parties.color")
            except Exception as e:
                print(f"Migration failed (constant_parties.color): {e}")

    for q_name in DEFAULT_QUEUES:
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
