import aiosqlite
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Dict, Any
from consts import CLASSES

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_NAME = "guild_bot.db"

# --- DATABASE INITIALIZATION (From bot.py) ---
# --- DATABASE INITIALIZATION REMOVED (Handled by database.py) ---
# async def init_db(): passed to global init

# --- HELPER FUNCTIONS ---

def get_intervals(start_date_str, end_date_str, period, count=1):
    """
    Generates a list of intervals [(label, start_dt, end_dt)]
    Period: 'day', 'week', 'month', 'year'
    """
    s_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    e_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    
    intervals = []
    
    current = s_date
    while current <= e_date:
        interval_start = current
        
        if period == 'day':
            interval_end = current + timedelta(days=count - 1)
            next_start = interval_end + timedelta(days=1)
            label = interval_start.strftime("%d.%m")
            
        elif period == 'week':
            # Logic: Align to real week chunks
            days_to_sunday = 6 - current.weekday()
            interval_end = current + timedelta(days=days_to_sunday)
            
            if count > 1:
                interval_end += timedelta(weeks=count-1)
                
            next_start = interval_end + timedelta(days=1)
            
            # Cap at e_date
            if interval_end > e_date:
                interval_end = e_date
                
            label = f"{interval_start.strftime('%d.%m')} - {interval_end.strftime('%d.%m')}"
            
        elif period == 'month':
            # Logic: Real months
            next_month_first = (current.replace(day=1) + timedelta(days=32)).replace(day=1)
            interval_end = next_month_first - timedelta(days=1)
            
            if count > 1:
                 # Simplified for now (loop if needed)
                 for _ in range(count - 1):
                     next_month_first = (next_month_first + timedelta(days=32)).replace(day=1)
                     interval_end = next_month_first - timedelta(days=1)
            
            next_start = interval_end + timedelta(days=1)
            
            if interval_end > e_date:
                interval_end = e_date
            
            # Label Russian Months if possible, but keep simple for now
            label = interval_start.strftime("%b %Y") 
            
        elif period == 'year':
            interval_end = current.replace(month=12, day=31)
            next_start = interval_end + timedelta(days=1)
             
            if interval_end > e_date:
                interval_end = e_date
            
            label = interval_start.strftime("%Y")

        else:
             break
             
        intervals.append({
            'label': label,
            'start': interval_start,
            'end': interval_end
        })
        
        current = next_start
        
    return intervals

async def get_last_update_time():
    """Gets the date of the freshest record in DB and converts to MSK (UTC+3)."""
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute("SELECT MAX(timestamp) FROM events")
        row = await cursor.fetchone()
        ts = row[0]
        if ts:
            # 1. Get date as UTC
            dt_utc = datetime.fromtimestamp(ts, timezone.utc)
            # 2. Add exactly 3 hours (MSK)
            dt_msk = dt_utc + timedelta(hours=3)
            return dt_msk.strftime('%d.%m.%Y %H:%M') + " (МСК)"
    return "Нет данных"

def analyze_stats(events):
    """
    Analyzes player event list.
    Returns a dictionary with all counters.
    """
    stats = {
        "s1": 0, "s2": 0, "s3": 0, "s4": 0, "s5": 0, "s6": 0, "s7": 0,
        "adepts": 0, "dances": 0,
        "total_gold": 0,
        "total_valor": 0
    }
    
    events.sort(key=lambda x: x[0])
    
    for i, (ts, val, etype) in enumerate(events):
        # Gold
        if etype == 2:
            stats['total_gold'] += val
            continue 
            
        # Valor
        if etype == 1:
            stats['total_valor'] += val
            
            # Stages
            if val == 4:
                is_dance = False
                # Check backward (< 20 min)
                if i > 0:
                    prev_ts, prev_val, prev_type = events[i-1]
                    if prev_type == 1 and prev_val == 2 and (ts - prev_ts) < 1200:
                        is_dance = True
                
                # Check forward (< 20 min)
                if not is_dance and i < len(events) - 1:
                    next_ts, next_val, next_type = events[i+1]
                    if next_type == 1 and next_val == 8 and (next_ts - ts) < 1200:
                        is_dance = True
                
                if is_dance: stats['dances'] += 1
                else: stats['s1'] += 1
            
            elif val == 6: stats['s2'] += 1
            elif val == 10: stats['s3'] += 1
            elif val == 14: stats['s4'] += 1
            elif val == 24: stats['s5'] += 1
            elif val == 40: stats['s6'] += 1
            elif val == 70: stats['s7'] += 1
            elif val == 7: stats['adepts'] += 1
            elif val in [2, 8]: stats['dances'] += 1
            
    return stats

async def get_data_from_db(start_date: str = None, end_date: str = None, classes: List[int] = None, group_period: str = None, group_count: int = 1):
    today = datetime.now()
    if not end_date: end_date = today.strftime('%Y-%m-%d')
    
    # Auto-select: Monday of current week
    if not start_date:
        days_to_subtract = today.weekday()
        monday = today - timedelta(days=days_to_subtract)
        start_date = monday.strftime('%Y-%m-%d')

    # Calculate intervals if grouping is requested
    intervals = []
    if group_period:
        intervals = get_intervals(start_date, end_date, group_period, group_count)
    
    async with aiosqlite.connect(DB_NAME) as conn:
        # Base SQL
        sql = """
            SELECT 
                p.role_id, 
                COALESCE(p.nickname, 'ID ' || p.role_id), 
                p.class_id,
                e.timestamp, 
                e.value, 
                e.event_type
            FROM players p
            LEFT JOIN events e ON p.role_id = e.role_id 
                AND e.event_type IN (1, 2)
                AND substr(e.event_date, 1, 10) >= ? 
                AND substr(e.event_date, 1, 10) <= ?
            WHERE p.in_clan = 1
        """
        params = [start_date, end_date]
        
        # Filter by classes
        if classes:
            placeholders = ",".join("?" * len(classes))
            sql += f" AND p.class_id IN ({placeholders})"
            params.extend(classes)

        cursor = await conn.execute(sql, tuple(params))
        raw_rows = await cursor.fetchall()

    # Grouping
    players_events = {}
    for rid, name, cid, ts, val, etype in raw_rows:
        if rid not in players_events:
            players_events[rid] = {"name": name, "class_id": cid, "events": []}
        players_events[rid]["events"].append((ts, val, etype))

    result = []
    for rid, data in players_events.items():
        # Global stats (Total)
        stats = analyze_stats(data["events"])
        stats["name"] = data["name"]
        stats["role_id"] = rid  
        stats["class_id"] = data["class_id"] 
        
        # Calculate stats for each interval
        if intervals:
            stats["interval_stats"] = []
            for interval in intervals:
                # Filter events for this interval
                # Use standard timestamp comparison 
                # (interval start/end are datetime objects, events have unix ts or need conversion?)
                # Wait, events have `ts` (unix timestamp)
                
                # Convert interval dates to timestamps
                # Use timezone.utc? DB timestamps are usually unix secs.
                # Assuming simple comparison
                ts_start = interval['start'].timestamp()
                # interval['end'] is at 00:00 of that day? No, our logic made it end date.
                # To capture the full end day, we need end_date + 23:59:59 or simply < next_day
                ts_end = (interval['end'] + timedelta(days=1)).timestamp()
                
                interval_events = [
                    ev for ev in data["events"] 
                    if ev[0] is not None and ts_start <= ev[0] < ts_end
                ]
                
                istats = analyze_stats(interval_events)
                stats["interval_stats"].append({
                    "label": interval["label"],
                    "valor": istats["total_valor"],
                    "gold": istats["total_gold"]
                })
        
        # Mapping Class
        cid = data["class_id"]
        if cid in CLASSES:
            cname, cemoji, cshort = CLASSES[cid]
            stats["class_icon"] = f"/static/icons/{cid}.png"
            stats["class_name"] = cname
        else:
            stats["class_icon"] = ""
            stats["class_name"] = ""
            
        result.append(stats)

    # Sort: First by s7, then by total valor
    result.sort(key=lambda x: (x.get('s7', 0), x.get('total_valor', 0)), reverse=True)
    
    # Return intervals too so frontend can build headers
    return result, start_date, end_date, intervals
