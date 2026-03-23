from datetime import datetime, timedelta, date
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import select, func, and_, or_, String

from consts import CLASSES
from database import User, Player, Character, AsyncSessionLocal, Event, ConstantParty, PartyMember, AFKHistory, Item
from logic.analytics import calculate_gold_thresholds, calculate_thresholds, get_gold_tier, get_valor_tier
from logic.helpers import is_newcomer
from web_database import get_data_from_db

# --- SHARED HELPERS ---

async def get_join_dates() -> Tuple[Dict[int, str], Dict[int, int]]:
    """
    Returns:
    1. join_dates: {role_id: first_seen_date_str}
    2. role_user_map: {role_id: user_id}
       Enriched with character linkage so all linked chars
       (main + twins) share the same user_id for AFK spreading.
    """
    async with AsyncSessionLocal() as session:
        # 1. Get initial data from players
        stmt_players = select(Player.role_id, Player.first_seen, Player.user_id).where(Player.in_clan == 1)
        result_players = await session.execute(stmt_players)
        join_data = result_players.all()

        # 2. Enrich role_user_map with character linkage
        stmt_links = (
            select(Character.user_id, Player.role_id)
            .join(Player, func.lower(func.trim(Character.nickname)) == func.lower(func.trim(Player.nickname)))
            .where(and_(Character.user_id.isnot(None), Player.in_clan == 1))
        )
        result_links = await session.execute(stmt_links)
        char_links = result_links.all()

    join_dates = {role_id: first_seen for role_id, first_seen, _ in join_data if first_seen}
    role_user_map = {role_id: user_id for role_id, _, user_id in join_data if user_id}

    # Add character linkage entries (don't overwrite existing)
    for uid, rid in char_links:
        if rid not in role_user_map:
            role_user_map[rid] = uid

    return join_dates, role_user_map

async def get_afk_map() -> Dict[int, List[Tuple[datetime, datetime, str]]]:
    """
    Returns: {key: [(start_dt, end_dt, reason), ...]}
    Keys are user_id (positive) for linked players,
    or -role_id (negative) for unlinked players with role_id-only AFK entries.
    """
    async with AsyncSessionLocal() as session:
        # 1. Current AFK (from users table)
        stmt_users = select(User.id, User.afk_start, User.afk_end, User.afk_reason).where(User.afk_start.isnot(None))
        result_users = await session.execute(stmt_users)
        afk_rows = result_users.all()

        # 2. History AFK
        stmt_history = select(AFKHistory.user_id, AFKHistory.role_id, AFKHistory.start_date, AFKHistory.end_date, AFKHistory.reason)
        result_history = await session.execute(stmt_history)
        afk_history_rows = result_history.all()

        # 3. Character linkage: role_id -> user_id
        stmt_links = (
            select(Player.role_id, Character.user_id)
            .join(Player, func.lower(func.trim(Character.nickname)) == func.lower(func.trim(Player.nickname)))
            .where(and_(Character.user_id.isnot(None), Player.in_clan == 1))
        )
        result_links = await session.execute(stmt_links)
        role_to_user = {r[0]: r[1] for r in result_links.all()}

    afk_map: Dict[int, List[Tuple[datetime, datetime, str]]] = {}

    def parse_date(date_val):
        if not date_val: return None
        if isinstance(date_val, (datetime, date)):
             if isinstance(date_val, date) and not isinstance(date_val, datetime):
                 return datetime.combine(date_val, datetime.min.time())
             return date_val
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
    async with AsyncSessionLocal() as session:
        stmt = (
            select(PartyMember.player_role_id, ConstantParty.name, ConstantParty.color)
            .join(ConstantParty, PartyMember.party_id == ConstantParty.id)
        )
        result = await session.execute(stmt)
        rows = result.all()
        
    party_map = {}
    for r_role_id, r_name, r_color in rows:
        rid = r_role_id
        if rid not in party_map: party_map[rid] = []
        party_map[rid].append({"name": r_name or "Без названия", "color": r_color or "#888888"})
    return party_map

async def get_main_nick_map() -> Dict[int, str]:
    """Returns {role_id: main_nickname} for characters that are alts."""
    async with AsyncSessionLocal() as session:
        # 1. Get all clan members from players
        stmt_players = select(Player.role_id, Player.user_id, Player.nickname, Player.is_alt).where(Player.in_clan == 1)
        result_players = await session.execute(stmt_players)
        player_rows = result_players.all()
        
        # 2. Get character linkage (much more reliable for twins)
        stmt_links = (
            select(Character.user_id, Player.role_id, Character.nickname, Character.is_main)
            .join(Player, func.lower(func.trim(Character.nickname)) == func.lower(func.trim(Player.nickname)))
            .where(and_(Character.user_id.isnot(None), Player.in_clan == 1))
        )
        result_links = await session.execute(stmt_links)
        char_links = result_links.all()

    # Build role -> user mapping and track is_main status
    role_to_user = {}
    is_main_status = {} # {role_id: bool}
    
    # First: from players table
    for rid, uid, nick, is_alt_val in player_rows:
        if uid:
            role_to_user[rid] = uid
        # Default is_main status if we don't find it in characters table
        is_main_status[rid] = (is_alt_val == 0)

    # Second: enrich/override from characters table
    for uid, rid, nick, is_main_val in char_links:
        role_to_user[rid] = uid
        is_main_status[rid] = bool(is_main_val)

    # Group characters by user_id and find the "true" main for each user
    user_to_main_nick = {}
    for rid, uid, nick, is_alt_val in player_rows:
        u_id = role_to_user.get(rid)
        if u_id and is_main_status.get(rid):
            user_to_main_nick[u_id] = nick
    
    # Map alts to their main's nickname.
    mapping = {}
    for rid, uid, nick, is_alt_val in player_rows:
        u_id = role_to_user.get(rid)
        if u_id and u_id in user_to_main_nick:
            main_nick = user_to_main_nick[u_id]
            if nick != main_nick:
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
            raw_jd = join_dates[role_id]
            if isinstance(raw_jd, (datetime, date)):
                jd_dt = raw_jd
                jd_str = jd_dt.strftime("%Y-%m-%d")
            else:
                jd_str = str(raw_jd).split()[0]
                try:
                    jd_dt = datetime.strptime(jd_str, "%Y-%m-%d")
                except:
                    jd_dt = None
            
            if jd_dt:
                if isinstance(jd_dt, date) and not isinstance(jd_dt, datetime):
                    jd_dt = datetime.combine(jd_dt, datetime.min.time())
                jd_diff = (today - jd_dt).days

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
            "adepts_details": r.get("adepts_details", []),
            "dances_details": r.get("dances_details", []),
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
            raw_jd = join_dates[role_id]
            if isinstance(raw_jd, (datetime, date)):
                jd_dt = raw_jd
                row["join_date"] = jd_dt.strftime("%Y-%m-%d")
            else:
                row["join_date"] = str(raw_jd).split()[0]
                try:
                    jd_dt = datetime.strptime(row["join_date"], "%Y-%m-%d")
                except:
                    jd_dt = None
            
            if jd_dt:
                if isinstance(jd_dt, date) and not isinstance(jd_dt, datetime):
                    jd_dt = datetime.combine(jd_dt, datetime.min.time())
                row["join_days_ago"] = (today - jd_dt).days
            else:
                row["join_days_ago"] = 0
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
    async with AsyncSessionLocal() as session:
        # 1. Base query using SQLAlchemy
        stmt = (
            select(
                Event.event_date,
                func.coalesce(Player.nickname, "ID " + func.cast(Event.role_id, String)).label("nickname"),
                Player.class_id,
                Event.raw_desc,
                Event.event_type,
                Event.role_id,
                Item.name.label("item_name"),
                Event.timestamp,
                Event.id
            )
            .join(Player, Event.role_id == Player.role_id, isouter=True)
            .join(Item, and_(Event.event_type == 0, Event.value == Item.id), isouter=True)
        )
        
        if start:
            if len(start) > 10:
                stmt = stmt.where(func.substr(Event.event_date, 1, 16) >= start)
            else:
                stmt = stmt.where(func.substr(Event.event_date, 1, 10) >= start)
        if end:
            if len(end) > 10:
                stmt = stmt.where(func.substr(Event.event_date, 1, 16) <= end)
            else:
                stmt = stmt.where(func.substr(Event.event_date, 1, 10) <= end)
                
        if class_list:
            stmt = stmt.where(Player.class_id.in_(class_list))

        if event_types:
            allowed = []
            for t in event_types:
                if t == "valor": allowed.append(1)
                elif t == "gold": allowed.append(2)
                elif t == "items": allowed.append(0)
                elif t == "roster": allowed.extend([5, 6, 7, 8, 9, 10])
            
            if allowed:
                stmt = stmt.where(Event.event_type.in_(allowed))

        stmt = stmt.order_by(Event.timestamp.desc()).limit(500)

        result_stmt = await session.execute(stmt)
        raw = result_stmt.all()

        # [FIX] Pre-fetch all nicknames for dynamic ID resolution in descriptions
        stmt_nicks = select(Player.role_id, Player.nickname).where(Player.nickname.isnot(None))
        result_nicks = await session.execute(stmt_nicks)
        id_to_nick = {r[0]: r[1] for r in result_nicks.all()}
    
    # Context Data
    join_dates, role_user_map = await get_join_dates()
    afk_map = await get_afk_map()
    today = datetime.now()

    import re
    id_pattern = re.compile(r"ID (\d+)")

    result = []
    for date_evt, name, cid, desc, etype, role_id, item_name, ts, event_id in raw:
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
            raw_jd = join_dates[role_id]
            if isinstance(raw_jd, (datetime, date)):
                jd_dt = raw_jd
                jd_str = jd_dt.strftime("%Y-%m-%d")
            else:
                jd_str = str(raw_jd).split()[0]
                try:
                    jd_dt = datetime.strptime(jd_str, "%Y-%m-%d")
                except:
                    jd_dt = None
            
            if jd_dt:
                if isinstance(jd_dt, date) and not isinstance(jd_dt, datetime):
                    jd_dt = datetime.combine(jd_dt, datetime.min.time())
                jd_diff = (today - jd_dt).days
            
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
            "afk_reason": afk_reason,
            "id": event_id
        })
        
    return result
