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
       Enriched with character linkage so all linked chars
       (main + twins) share the same user_id for AFK spreading.
    """
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute("SELECT role_id, first_seen, user_id FROM players WHERE in_clan = 1")
        join_data = await cursor.fetchall()

        # Enrich role_user_map with character linkage
        # This ensures twins (alts) linked via the characters table
        # inherit the same user_id for AFK status spreading
        cursor = await conn.execute("""
            SELECT c.user_id, p.role_id
            FROM characters c
            JOIN players p ON LOWER(TRIM(c.nickname)) = LOWER(TRIM(p.nickname))
            WHERE c.user_id IS NOT NULL AND p.in_clan = 1
        """)
        char_links = await cursor.fetchall()

    join_dates = {role_id: first_seen for role_id, first_seen, _ in join_data if first_seen}
    role_user_map = {role_id: user_id for role_id, _, user_id in join_data if user_id}

    # Add character linkage entries (don't overwrite existing)
    for uid, rid in char_links:
        if rid not in role_user_map:
            role_user_map[rid] = uid

    return join_dates, role_user_map

async def get_afk_map() -> Dict[int, List[Tuple[datetime, datetime]]]:
    """
    Returns: {key: [(start_dt, end_dt), ...]}
    Keys are user_id (positive) for linked players,
    or -role_id (negative) for unlinked players with role_id-only AFK entries.
    """
    async with aiosqlite.connect(DB_NAME) as conn:
        # 1. Current AFK (from users table)
        cursor = await conn.execute("SELECT id, afk_start, afk_end, afk_reason FROM users WHERE afk_start IS NOT NULL")
        afk_rows = await cursor.fetchall()

        # 2. History AFK (includes user_id and role_id)
        cursor = await conn.execute("SELECT user_id, role_id, start_date, end_date, reason FROM afk_history")
        afk_history_rows = await cursor.fetchall()

        # 3. Character linkage: role_id -> user_id (for promoting role-only AFK to user)
        cursor = await conn.execute("""
            SELECT p.role_id, c.user_id
            FROM characters c
            JOIN players p ON LOWER(TRIM(c.nickname)) = LOWER(TRIM(p.nickname))
            WHERE c.user_id IS NOT NULL AND p.in_clan = 1
        """)
        role_to_user = {r[0]: r[1] for r in await cursor.fetchall()}

    afk_map: Dict[int, List[Tuple[datetime, datetime]]] = {}

    def parse_date(date_val):
        if not date_val: return None
        if isinstance(date_val, datetime): return date_val
        try:
            s_val = str(date_val)
            if "." in s_val: return datetime.strptime(s_val, "%Y-%m-%d %H:%M:%S.%f")
            elif " " in s_val: return datetime.strptime(s_val, "%Y-%m-%d %H:%M:%S")
            else: return datetime.strptime(s_val, "%Y-%m-%d")
        except: return None

    def add_period(key, s_dt, e_dt, reason=None):
        if key is None: return
        if key not in afk_map: afk_map[key] = []
        afk_map[key].append((s_dt, e_dt, reason))

    # Users table entries (keyed by user_id)
    for uid, start_ts, end_ts, reason in afk_rows:
        s_dt = parse_date(start_ts)
        e_dt = parse_date(end_ts) or s_dt
        if s_dt and e_dt:
            add_period(uid, s_dt, e_dt, reason)

    # History entries
    for uid, rid, start_ts, end_ts, reason in afk_history_rows:
        s_dt = parse_date(start_ts)
        e_dt = parse_date(end_ts) or s_dt
        if s_dt and e_dt:
            if uid:
                add_period(uid, s_dt, e_dt, reason)
            elif rid:
                # Role-only entry: also promote to user_id if character is linked
                linked_uid = role_to_user.get(rid)
                if linked_uid:
                    add_period(linked_uid, s_dt, e_dt, reason)
                else:
                    add_period(-rid, s_dt, e_dt, reason)

    return afk_map

def get_afk_display_info(role_id: int, role_user_map: Dict[int, int], afk_map: Dict[int, List], start_dt: Optional[datetime] = None, end_dt: Optional[datetime] = None) -> Tuple[bool, Optional[str], Optional[str]]:
    if not role_id: return False, None, None
    uid = role_user_map.get(role_id)
    # Check by user_id first, then fall back to -role_id for unlinked players
    if uid and uid in afk_map:
        pass  # uid is valid
    elif -role_id in afk_map:
        uid = -role_id
    else:
        return False, None, None
    
    periods = afk_map[uid]
    if not periods: return False, None, None

    # Filter periods that overlap with [start_dt, end_dt]
    overlapping_periods = []
    if start_dt and end_dt:
        # User requested specific period
        for s, e, r in periods:
            if max(s, start_dt) <= min(e, end_dt):
                overlapping_periods.append((s, e, r))
    else:
        # No range provided? Fallback to "currently AFK" check or just show most recent
        # Given the requirements, we likely always have start/end for table data.
        overlapping_periods = periods

    if not overlapping_periods:
        return False, None, None

    # Return most recent among overlapping
    sorted_periods = sorted(overlapping_periods, key=lambda x: x[1], reverse=True)
    s, e, r = sorted_periods[0]
    return True, f"{s.strftime('%d.%m')} - {e.strftime('%d.%m')}", r

async def get_party_map() -> Dict[int, List[Dict[str, str]]]:
    """Returns {role_id: [{'name': str, 'color': str}, ...]}"""
    async with aiosqlite.connect(DB_NAME) as conn:
        conn.row_factory = aiosqlite.Row
        sql = """
            SELECT pm.player_role_id, cp.name, cp.color
            FROM party_members pm
            JOIN constant_parties cp ON pm.party_id = cp.id
        """
        cursor = await conn.execute(sql)
        rows = await cursor.fetchall()
        
    party_map = {}
    for r in rows:
        rid = r["player_role_id"]
        if rid not in party_map: party_map[rid] = []
        party_map[rid].append({"name": r["name"] or "Без названия", "color": r["color"] or "#888888"})
    return party_map

async def get_main_nick_map() -> Dict[int, str]:
    """Returns {role_id: main_nickname} for characters that are alts."""
    async with aiosqlite.connect(DB_NAME) as conn:
        conn.row_factory = aiosqlite.Row
        # 1. Get all clan members from players
        cursor = await conn.execute("SELECT role_id, user_id, nickname, is_alt FROM players WHERE in_clan = 1")
        player_rows = await cursor.fetchall()
        
        # 2. Get character linkage (much more reliable for twins)
        cursor = await conn.execute("""
            SELECT c.user_id, p.role_id, c.nickname, c.is_main
            FROM characters c
            JOIN players p ON LOWER(TRIM(c.nickname)) = LOWER(TRIM(p.nickname))
            WHERE c.user_id IS NOT NULL AND p.in_clan = 1
        """)
        char_links = await cursor.fetchall()

    # Build role -> user mapping and track is_main status from characters table
    role_to_user = {}
    is_main_status = {} # {role_id: bool}
    
    # First: from players table
    for r in player_rows:
        rid = r["role_id"]
        if r["user_id"]:
            role_to_user[rid] = r["user_id"]
        # Default is_main status if we don't find it in characters table
        is_main_status[rid] = (r["is_alt"] == 0)

    # Second: enrich/override from characters table (more reliable)
    for r in char_links:
        rid = r["role_id"]
        uid = r["user_id"]
        role_to_user[rid] = uid
        is_main_status[rid] = bool(r["is_main"])

    # Group characters by user_id and find the "true" main for each user
    user_to_main_nick = {}
    for r in player_rows:
        rid = r["role_id"]
        uid = role_to_user.get(rid)
        if uid and is_main_status.get(rid):
            user_to_main_nick[uid] = r["nickname"]
    
    # Map alts to their main's nickname. 
    # An alt is any character that is NOT the main.
    mapping = {}
    for r in player_rows:
        rid = r["role_id"]
        uid = role_to_user.get(rid)
        if uid and uid in user_to_main_nick:
            main_nick = user_to_main_nick[uid]
            if r["nickname"] != main_nick:
                mapping[rid] = main_nick
                
    return mapping

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
    party_map = await get_party_map()
    main_nicks = await get_main_nick_map()

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
        is_afk, afk_text, afk_reason = get_afk_display_info(role_id, role_user_map, afk_map, d1, d2)

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
            "user_id": r.get("user_id"),
            "is_alt": bool(r.get("is_alt", 0)),
            "main_nickname": main_nicks.get(role_id),
            "parties": party_map.get(role_id, []),
            "cp_id": r.get("cp_id"),
            "cp_color": r.get("cp_color"),
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
            "afk_reason": afk_reason,
            "join_date": jd_str,
            "join_days_ago": jd_diff,
            "valor_tier": v_tier,
            "gold_tier": g_tier,
            "s1_details": r.get("s1_details", []),
            "s2_details": r.get("s2_details", []),
            "s3_details": r.get("s3_details", []),
            "s4_details": r.get("s4_details", []),
            "s5_details": r.get("s5_details", []),
            "s6_details": r.get("s6_details", []),
            "s7_details": r.get("s7_details", []),
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
    party_map = await get_party_map()
    main_nicks = await get_main_nick_map()

    # Filter Classes
    if class_list:
        rows_raw = [r for r in rows_raw if r["class_id"] in class_list]

    final_rows = []

    for r in rows_raw:
        role_id = r["role_id"]
        
        # Helper wrappers
        try:
            m_s_dt = datetime.strptime(m_s, "%Y-%m-%d")
            m_e_dt = datetime.strptime(m_e, "%Y-%m-%d")
        except:
            m_s_dt, m_e_dt = None, None
            
        is_nc = is_newcomer(role_id, join_dates, m_s)
        is_afk, afk_text, afk_reason = get_afk_display_info(role_id, role_user_map, afk_map, m_s_dt, m_e_dt)

        # Newcomer Filter
        if newcomers_mode == "only" and not is_nc: continue
        if newcomers_mode == "hide" and is_nc: continue

        row = dict(r)
        row["is_mine"] = (r.get("name", "").lower().strip() in my_nicks)
        row["is_newcomer"] = is_nc
        row["is_afk"] = is_afk
        row["afk_dates"] = afk_text
        row["afk_reason"] = afk_reason
        row["main_nickname"] = main_nicks.get(role_id)
        row["parties"] = party_map.get(role_id, [])
        
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

            # Get AFK periods for either UID (linked) or -ROLE_ID (unlinked)
            uid = role_user_map.get(role_id)
            u_afk_periods = []
            if uid:
                u_afk_periods.extend(afk_map.get(uid, []))
            # Also check if there are AFK entries tied specifically to this role_id (unlinked)
            u_afk_periods.extend(afk_map.get(-role_id, []))

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
                        overlap_start = max(i_s.date(), jd_dt.date())
                        overlap_end = min(i_e.date(), nc_end.date())
                        if overlap_start <= overlap_end:
                            istat["is_newcomer_stay"] = True

                    # 3. AFK Stay
                    for a_s, a_e, _ in u_afk_periods:
                        # Use .date() to avoid midnight mismatch
                        if max(i_s.date(), a_s.date()) <= min(i_e.date(), a_e.date()):
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
            elif t == "roster": allowed.extend([5, 6, 7, 8, 9, 10])
        
        if allowed:
            placeholders = ",".join("?" for _ in allowed)
            sql += f" AND e.event_type IN ({placeholders})"
            params.extend(allowed)

    sql += " ORDER BY e.timestamp DESC LIMIT 500"

    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(sql, tuple(params))
        raw = await cursor.fetchall()

        # [FIX] Pre-fetch all nicknames for dynamic ID resolution in descriptions
        cursor = await conn.execute("SELECT role_id, nickname FROM players WHERE nickname IS NOT NULL")
        id_to_nick = {r[0]: r[1] for r in await cursor.fetchall()}
    
    # Context Data
    join_dates, role_user_map = await get_join_dates()
    afk_map = await get_afk_map()
    today = datetime.now()

    import re
    id_pattern = re.compile(r"ID (\d+)")

    result = []
    for date_evt, name, cid, desc, etype, role_id, item_name, ts in raw:
        # [FIX] Dynamic ID resolution in description
        if desc and "ID " in desc:
            matches = id_pattern.findall(desc)
            for m_id_str in matches:
                try:
                    m_id = int(m_id_str)
                    if m_id in id_to_nick:
                        desc = desc.replace(f"ID {m_id}", id_to_nick[m_id])
                except: pass

        icon = f"/static/icons/{cid}.png" if cid in CLASSES else ""
        cname = CLASSES[cid][0] if cid in CLASSES else ""
        is_mine = name and name.lower().strip() in my_nicks
        
        # Join Date logic
        jd_str = ""
        jd_diff = 0
        if role_id in join_dates:
            raw_jd = join_dates[role_id].split()[0]
            jd_str = raw_jd
            try:
                jd_dt = datetime.strptime(raw_jd, "%Y-%m-%d")
                jd_diff = (today - jd_dt).days
            except: pass
            
        # AFK logic
        try:
            s_dt = datetime.strptime(start, "%Y-%m-%d") if start else None
            e_dt = datetime.strptime(end, "%Y-%m-%d") if end else None
        except:
            s_dt, e_dt = None, None
            
        is_afk, afk_text, afk_reason = get_afk_display_info(role_id, role_user_map, afk_map, s_dt, e_dt)

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
            "timestamp": ts,
            "join_date": jd_str,
            "join_days_ago": jd_diff,
            "is_afk": is_afk,
            "afk_dates": afk_text,
            "afk_reason": afk_reason
        })
        
    return result
