from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime

Base = declarative_base()

# --- МОДЕЛИ ---

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String)
    is_master = Column(Boolean, default=False)
    is_banned = Column(Boolean, default=False)
    personal_limit = Column(Integer, nullable=True) 
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
    user = relationship("User")
    queue = relationship("QueueType")

class RewardHistory(Base):
    __tablename__ = 'reward_history'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    character_name = Column(String)
    queue_name = Column(String)
    issued_by = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

class ScheduledAnnouncement(Base):
    __tablename__ = 'announcements'
    id = Column(Integer, primary_key=True)
    text = Column(String)
    schedule_type = Column(String)
    run_time = Column(String)
    days_of_week = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

# --- ИНИЦИАЛИЗАЦИЯ ---

engine = create_engine('sqlite:///guild_bot.db', echo=False)
Session = sessionmaker(bind=engine)
session = Session()

def init_db():
    Base.metadata.create_all(engine)
    
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
        
    # Иначе берем общий из настроек
    setting = session.query(Settings).filter_by(key="default_limit").first()
    return int(setting.value) if setting else 1