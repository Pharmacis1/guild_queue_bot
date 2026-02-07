from datetime import datetime, timedelta, date
from typing import List, Optional, Tuple, Dict, Any
import aiosqlite

from consts import CLASSES
from database import User, session
from web_database import DB_NAME, get_data_from_db, get_last_update_time
from logic.analytics import calculate_gold_thresholds, calculate_thresholds, get_gold_tier, get_valor_tier
from logic.helpers import is_newcomer

# --- SHARED HELPERS ---

async def get_join_dates() -> Tuple[Dict[int, str], Dict[int, int]]:
    """
    Returns:
    1. join_dates: {role_id: first_seen_date_str}
    2. role_user_map: {role_id: user_id}
    """
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute("SELECT role_id, first_seen, user_id FROM players WHERE in_clan = 1")
        join_data = await cursor.fetchall()
        
    join_dates = {role_id: first_seen for role_id, first_seen, _ in join_data if first_seen}
    role_user_map = {role_id: user_id for role_id, _, user_id in join_data if user_id}
    return join_dates, role_user_map

async def get_afk_map() -> Dict[int, List[Tuple[datetime, datetime]]]:
    """
    Returns: {user_id: [(start_dt, end_dt), ...]}
    """
    async with aiosqlite.connect(DB_NAME) as conn:
        # 1. Current AFK
        cursor = await conn.execute("SELECT id, afk_start, afk_end FROM users WHERE afk_start IS NOT NULL")
        afk_rows = await cursor.fetchall()

        # 2. History AFK
        cursor = await conn.execute("SELECT user_id, start_date, end_date FROM afk_history")
        afk_history_rows = await cursor.fetchall()

    afk_map = {}

    def parse_date(date_val):
        if not date_val: return None
        if isinstance(date_val, datetime): return date_val
        try:
            s_val = str(date_val)
            if "." in s_val: return datetime.strptime(s_val, "%Y-%m-%d %H:%M:%S.%f")
            elif " " in s_val: return datetime.strptime(s_val, "%Y-%m-%d %H:%M:%S")
            else: return datetime.strptime(s_val, "%Y-%m-%d")
        except: return None

    all_rows = [(uid, s, e) for uid, s, e in afk_rows] + [(uid, s, e) for uid, s, e in afk_history_rows]

    for uid, start_ts, end_ts in all_rows:
        s_dt = parse_date(start_ts)
        e_dt = parse_date(end_ts) or s_dt
        if s_dt and e_dt:
            if uid not in afk_map: afk_map[uid] = []
            afk_map[uid].append((s_dt, e_dt))
            
    return afk_map

def get_afk_display_info(role_id: int, role_user_map: Dict[int, int], afk_map: Dict[int, List]) -> Tuple[bool, Optional[str]]:
    if not role_id: return False, None
    uid = role_user_map.get(role_id)
    if not uid or uid not in afk_map: return False, None
    
    periods = afk_map[uid]
    if not periods: return True, None # Should not happen if key exists

    # Return most recent
    sorted_periods = sorted(periods, key=lambda x: x[1], reverse=True)
    s, e = sorted_periods[0]
    return True, f"{s.strftime('%d.%m')} - {e.strftime('%d.%m')}"

# --- DATA PROCESSORS ---

async def get_kh_table_data(
    start: Optional[str], 
    end: Optional[str], 
    class_list: Optional[List[int]], 
    newcomers_mode: Optional[str],
    my_nicks: set
) -> dict:
    
    # Defaults
    today = datetime.now()
    if not start and not end:
        days_to_monday = today.weekday()
        start = (today - timedelta(days=days_to_monday)).strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
    
    # DB Fetch
    rows_raw, real_s, real_e, _ = await get_data_from_db(start, end, None, None, 1) # Force group_count=1 for KH
    print(f"DEBUG: get_data_from_db returned {len(rows_raw)} raw rows")

    # Filter Classes
    if class_list:
        rows_raw = [r for r in rows_raw if r["class_id"] in class_list]
        print(f"DEBUG: After class filter ({class_list}): {len(rows_raw)} rows")
    else:
        print("DEBUG: No class filter")


    # Context Data
    join_dates, role_user_map = await get_join_dates()
    afk_map = await get_afk_map()

    # Tiers logic
    active_valors = sorted([r["total_valor"] for r in rows_raw if r["total_valor"] > 0])
    active_gold = sorted([r["total_gold"] for r in rows_raw if r["total_gold"] > 0])
    t_v = calculate_thresholds(active_valors)
    t_g = calculate_gold_thresholds(active_gold)

    try:
        d1 = datetime.strptime(real_s, "%Y-%m-%d")
        d2 = datetime.strptime(real_e, "%Y-%m-%d")
        days_diff = (d2 - d1).days + 1
    except: days_diff = 1

    final_rows = []
    
    for r in rows_raw:
        role_id = r["role_id"]
        
        # Newcomer check
        is_nc = is_newcomer(role_id, join_dates, real_s)
        if newcomers_mode == "only" and not is_nc: continue
        if newcomers_mode == "hide" and is_nc: continue

        # Join Date
        jd_str = ""
        jd_diff = 0
        if role_id in join_dates:
            raw_jd = join_dates[role_id].split()[0]
            jd_str = raw_jd
            try:
                jd_dt = datetime.strptime(raw_jd, "%Y-%m-%d")
                jd_diff = (today - jd_dt).days
            except: pass

        # AFK
        is_afk, afk_text = get_afk_display_info(role_id, role_user_map, afk_map)

        # Tiers
        v_tier = get_valor_tier(r["total_valor"], active_valors, t_v, days_diff)
        g_tier = get_gold_tier(r["total_gold"], active_gold, t_g, days_diff)
        
        # Validate tiers are strings (force conversion)
        v_tier = str(v_tier or "")
        g_tier = str(g_tier or "")

        final_rows.append({
            "role_id": role_id,
            "name": r["name"],
            "class_id": r["class_id"],
            "s1": r.get("s1", 0),
            "s2": r.get("s2", 0),
            "s3": r.get("s3", 0),
            "s4": r.get("s4", 0),
            "s5": r.get("s5", 0),
            "s6": r.get("s6", 0),
            "s7": r.get("s7", 0),
            "adepts": r.get("adepts", 0),
            "dances": r.get("dances", 0),
            "total_valor": r["total_valor"],
            "total_gold": r["total_gold"],
            "is_mine": (r["name"].lower().strip() in my_nicks),
            "is_newcomer": is_nc,
            "is_afk": is_afk,
            "afk_dates": afk_text,
            "join_date": jd_str,
            "join_days_ago": jd_diff,
            "valor_tier": v_tier,
            "gold_tier": g_tier
        })

    print(f"DEBUG: Returning {len(final_rows)} rows to API")
    return {
        "rows": final_rows,
        "start_date": real_s,
        "end_date": real_e
    }

async def get_money_table_data(
    start: Optional[str],
    end: Optional[str],
    class_list: Optional[List[int]],
    newcomers_mode: Optional[str],
    group_period: Optional[str],
    group_count: int,
    my_nicks: set
):
    # Money Default Dates: Last 7 Days
    today = datetime.now()
    if not start and not end:
        start_7days = today - timedelta(days=6)
        start = start_7days.strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")

    # DB Fetch
    rows_raw, m_s, m_e, intervals = await get_data_from_db(
        start, end, None, group_period, group_count
    )

    # Context Data
    join_dates, role_user_map = await get_join_dates()
    afk_map = await get_afk_map()

    # Filter Classes
    if class_list:
        rows_raw = [r for r in rows_raw if r["class_id"] in class_list]

    final_rows = []

    for r in rows_raw:
        role_id = r["role_id"]
        
        # Helper wrappers
        is_nc = is_newcomer(role_id, join_dates, m_s)
        is_afk, afk_text = get_afk_display_info(role_id, role_user_map, afk_map)

        # Newcomer Filter
        if newcomers_mode == "only" and not is_nc: continue
        if newcomers_mode == "hide" and is_nc: continue

        row = dict(r)
        row["is_mine"] = (r.get("name", "").lower().strip() in my_nicks)
        row["is_newcomer"] = is_nc
        row["is_afk"] = is_afk
        row["afk_dates"] = afk_text
        
        # Join Date
        if role_id in join_dates:
            raw_jd = join_dates[role_id].split()[0]
            row["join_date"] = raw_jd
            try:
                jd_dt = datetime.strptime(raw_jd, "%Y-%m-%d")
                row["join_days_ago"] = (today - jd_dt).days
            except: row["join_days_ago"] = 0
        else:
            row["join_date"] = ""
            row["join_days_ago"] = 0

        # Intervals Logic
        if "interval_stats" in row:
            jd_dt = None
            if row["join_date"]:
                try: jd_dt = datetime.strptime(row["join_date"], "%Y-%m-%d")
                except: pass

            uid = role_user_map.get(role_id)
            u_afk_periods = afk_map.get(uid, []) if uid else []

            for istat in row["interval_stats"]:
                i_s = istat.get("start")
                i_e = istat.get("end")
                istat["is_pre_join"] = False
                istat["is_newcomer_stay"] = False
                istat["is_afk_stay"] = False

                if i_s and i_e:
                    # 1. Pre-Join
                    if jd_dt and i_e.date() < jd_dt.date():
                        istat["is_pre_join"] = True

                    # 2. Newcomer Stay (first 7 days)
                    if jd_dt:
                        nc_end = jd_dt + timedelta(days=6)
                        overlap_start = max(i_s, jd_dt)
                        overlap_end = min(i_e, timedelta(days=1, seconds=-1) + nc_end)
                        if overlap_start <= overlap_end:
                            istat["is_newcomer_stay"] = True

                    # 3. AFK Stay
                    for a_s, a_e in u_afk_periods:
                        if max(i_s, a_s) <= min(i_e, a_e):
                            istat["is_afk_stay"] = True
                            break

        final_rows.append(row)

    return {
        "rows": final_rows,
        "intervals": intervals,
        "start_date": m_s,
        "end_date": m_e,
        "group_period": group_period,
        "group_count": group_count
    }

async def get_history_data(
    start: Optional[str],
    end: Optional[str],
    class_list: Optional[List[int]],
    event_types: Optional[List[str]],
    my_nicks: set
):
    sql = """
        SELECT e.event_date, COALESCE(p.nickname, 'ID '||e.role_id), p.class_id, e.raw_desc, e.event_type, e.role_id, i.name, e.timestamp 
        FROM events e 
        LEFT JOIN players p ON e.role_id = p.role_id 
        LEFT JOIN items i ON (e.event_type = 0 AND e.value = i.id)
        WHERE 1=1
    """
    params = []
    
    if start:
        sql += " AND substr(e.event_date, 1, 10) >= ?"
        params.append(start)
    if end:
        sql += " AND substr(e.event_date, 1, 10) <= ?"
        params.append(end)
        
    if class_list:
        placeholders = ",".join("?" for _ in class_list)
        sql += f" AND p.class_id IN ({placeholders})"
        params.extend(class_list)

    if event_types:
        allowed = []
        for t in event_types:
            if t == "valor": allowed.append(1)
            elif t == "gold": allowed.append(2)
            elif t == "items": allowed.append(0)
            elif t == "roster": allowed.extend([6, 8, 10])
        
        if allowed:
            placeholders = ",".join("?" for _ in allowed)
            sql += f" AND e.event_type IN ({placeholders})"
            params.extend(allowed)

    sql += " ORDER BY e.timestamp DESC LIMIT 500"

    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(sql, tuple(params))
        raw = await cursor.fetchall()
    
    result = []
    for date_evt, name, cid, desc, etype, role_id, item_name, ts in raw:
        icon = f"/static/icons/{cid}.png" if cid in CLASSES else ""
        cname = CLASSES[cid][0] if cid in CLASSES else ""
        is_mine = name and name.lower().strip() in my_nicks
        
        result.append({
            "date": date_evt,
            "name": name,
            "class_id": cid,
            "class_name": cname,
            "desc": desc,
            "type": etype,
            "role_id": role_id,
            "item_name": item_name,
            "is_mine": is_mine,
            "timestamp": ts
        })
        
    return result
