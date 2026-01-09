from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime

Base = declarative_base()

# 1. Таблица пользователей
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String)
    is_master = Column(Boolean, default=False)
    is_banned = Column(Boolean, default=False)
    
    # НОВОЕ ПОЛЕ: Личный лимит. Если NULL (None), то используется общий.
    personal_limit = Column(Integer, nullable=True) 
    
    characters = relationship("Character", back_populates="user", cascade="all, delete-orphan")

# 2. НОВАЯ ТАБЛИЦА: Глобальные настройки
class Settings(Base):
    __tablename__ = 'settings'
    key = Column(String, primary_key=True) # Например "default_limit"
    value = Column(String) # Например "1"

# ... (Остальные классы: Character, QueueType, QueueEntry, RewardHistory, ScheduledAnnouncement - БЕЗ ИЗМЕНЕНИЙ)
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

# НОВОЕ ПОЛЕ: is_locked = закрыта для записи (видят, но нажать нельзя)
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

# Инициализация
engine = create_engine('sqlite:///guild_bot.db', echo=False)
Session = sessionmaker(bind=engine)
session = Session()

def init_db():
    Base.metadata.create_all(engine)
    
    # 1. Создаем дефолтные очереди, если нет
    queues = [
        "Камень доблести", "Метеориты", "Жемчужины Фу Си", "Опыт в диск",
        "Проходки в УФ", "Знаки Единства", "Колода карт", "Сущность карты",
        "Камень божества", "Камни бессмертных", "Цилинь"
    ]
    for q_name in queues:
        if not session.query(QueueType).filter_by(name=q_name).first():
            session.add(QueueType(name=q_name))
            
    # 2. Создаем дефолтный глобальный лимит (если нет)
    if not session.query(Settings).filter_by(key="default_limit").first():
        session.add(Settings(key="default_limit", value="1"))
        
    session.commit()