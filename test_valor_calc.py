import asyncio
import os
import sys
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, func
from sqlalchemy.orm import sessionmaker, declarative_base

# 1. Setup Mock Models (aligned with database.py)
Base = declarative_base()

class Player(Base): 
    __tablename__ = 'players'
    role_id = Column(Integer, primary_key=True)
    nickname = Column(String)

class Event(Base): 
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True)
    role_id = Column(Integer)
    timestamp = Column(Integer)
    event_date = Column(String) # YYYY-MM-DD HH:MM:SS
    event_type = Column(Integer) # 1 = Valor, 2 = Gold
    value = Column(Integer)
    raw_desc = Column(String)

# 2. Setup DB
engine = create_engine('sqlite:///:memory:', echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# 3. Validation Logic (copied from handlers/admin.py)
def get_weekly_valor_map_simulated(nicknames, session_obj):
    if not nicknames: return {}
    
    # Calculate Start of Week (Monday)
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    start_date = monday.strftime('%Y-%m-%d')
    print(f"DEBUG: Calculated Start Date (Monday) = {start_date}")
    
    # Resolve Nicknames -> Role IDs
    players = session_obj.query(Player).filter(Player.nickname.in_(nicknames)).all()
    if not players: return {}
    
    role_map = {p.role_id: p.nickname for p in players}
    role_ids = list(role_map.keys())
    
    # Query: Sum value where type=1 AND date >= start_date
    events = session_obj.query(Event.role_id, func.sum(Event.value)).filter(
        Event.event_type == 1,
        Event.role_id.in_(role_ids),
        func.substr(Event.event_date, 1, 10) >= start_date
    ).group_by(Event.role_id).all()
    
    result = {}
    for nick in nicknames: result[nick] = 0 # Default 0 (or -1 if not found, but logic sets 0 for players)
    
    for rid, total in events:
        if rid in role_map:
            result[role_map[rid]] = total or 0
    return result

def run_test():
    print("--- Starting Valor Calculation Test ---")
    
    # A. Create Player
    p = Player(role_id=100, nickname="Hero")
    session.add(p)
    session.commit()
    
    # B. define Dates
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d %H:%M:%S')
    
    # Last week (ensure it's strictly before this week's Monday)
    # If today is Monday, last week is -7 days. 
    # Logic: Monday of this week
    monday_date = now - timedelta(days=now.weekday())
    monday_date = monday_date.replace(hour=0, minute=0, second=0, microsecond=0)
    
    last_week_date = monday_date - timedelta(days=2) # 2 days before this Monday
    last_week_str = last_week_date.strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"DEBUG: Current Time: {today_str}")
    print(f"DEBUG: Old Event Time: {last_week_str}")

    events_to_add = [
        # 1. Valid Valor (Type 1, Today) -> +50
        Event(role_id=100, event_date=today_str, event_type=1, value=50, raw_desc="Valid Valor 1"),
        
        # 2. Valid Valor (Type 1, Today) -> +25
        Event(role_id=100, event_date=today_str, event_type=1, value=25, raw_desc="Valid Valor 2"),
        
        # 3. Gold (Type 2, Today) -> SHOULD IGNORE
        Event(role_id=100, event_date=today_str, event_type=2, value=1000, raw_desc="Gold Event"),
        
        # 4. Old Valor (Type 1, Last Week) -> SHOULD IGNORE
        Event(role_id=100, event_date=last_week_str, event_type=1, value=999, raw_desc="Old Valor"),
    ]
    
    session.add_all(events_to_add)
    session.commit()
    
    # C. Run
    result = get_weekly_valor_map_simulated(["Hero"], session)
    
    # D. Verify
    expected_valor = 50 + 25 # = 75
    actual_valor = result.get("Hero", 0)
    
    print(f"\nRESULTS:")
    print(f"Player: Hero")
    print(f"Expected: {expected_valor}")
    print(f"Actual:   {actual_valor}")
    
    if expected_valor == actual_valor:
        print("[OK] SUCCESS: Calculation matches expectations.")
    else:
        print("[FAIL] FAILURE: Arithmetic mismatch.")
        if actual_valor >= 999:
            print("   -> It seems old events were included.")
        if actual_valor >= 1000:
            print("   -> It seems Gold events were included.")

if __name__ == "__main__":
    run_test()
