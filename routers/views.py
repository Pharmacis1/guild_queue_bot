import os
from datetime import date, datetime, timedelta
from typing import List

import aiosqlite
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from consts import CLASSES
from logic.analytics import calculate_gold_thresholds, calculate_thresholds, get_gold_tier, get_valor_tier
from web_database import DB_NAME, get_data_from_db, get_last_update_time

router = APIRouter()
templates = Jinja2Templates(directory="templates")

BOT_USERNAME = os.getenv("BOT_USERNAME", "my_pharmacis_bot")

@router.get("/", response_class=HTMLResponse)
async def read_root(
    request: Request, 
    # KH Params
    kh_start: str = None,
    kh_end: str = None,
    kh_classes: List[int] = Query(None),
    kh_newcomers: str = None,
    
    # Money Params
    money_start: str = None,
    money_end: str = None,
    money_classes: List[int] = Query(None),
    money_newcomers: str = None,
    money_group_period: str = None,
    money_group_count: int = 1,

    # Legacy/Global Fallbacks (for compatibility/initial load)
    start: str = None,
    end: str = None,
    classes: List[int] = Query(None),
    newcomers: str = None,
    group_period: str = None,
    group_count: int = 1,

    # History Params
    history_start: str = None,
    history_end: str = None,
    history_classes: List[int] = Query(None),
    history_types: List[str] = Query(None),
):
  try:
    # --- AUTH CHECK RESTORED ---
    from database import User, session
    
    # Default values for public access (Guest Mode)
    user_id = request.session.get('user_id')
    import logging
    logging.info(f"DEBUG VIEWS: Session Retrieved user_id: {user_id}")
    u = None
    my_nicks = set()
    is_authenticated = False
    is_admin = False
    user_nickname = "Guest"
    user_avatar = "/static/img/spider_arcane_ruby_transparent.png"
    
    if user_id:
        # Check if user exists in DB
        u = session.query(User).filter_by(telegram_id=user_id).first()
        if u:
            is_authenticated = True
            user_nickname = u.username or f"User {user_id}"
            user_avatar = u.avatar_url or user_avatar
            is_admin = u.is_master # Admin if is_master is True
            
            # Debug Chars
            import logging
            logging.info(f"DEBUG AUTH: User {u.username} ({user_id}) - Chars: {[c.nickname for c in u.characters]}")
            
            # Load characters for highlighting
            my_nicks = {c.nickname.lower().strip() for c in u.characters if c.nickname}
            
            # Find main character for display name
            main_char = next((c for c in u.characters if c.is_main), None)
            if main_char:
                user_nickname = main_char.nickname
            elif u.characters:
                 # Fallback to first character if no main is explicitly set but chars exist
                 user_nickname = u.characters[0].nickname
            # Else keep telegram username/id
        else:
            # Session exists but user not in DB (weird), treat as guest
            request.session.pop('user_id', None)

    # Auth OK (or Guest OK)
    
    # DEBUG
    print(f"DEBUG: history_types={history_types}")

    today = datetime.now()

    # --- 1. KH CONTEXT SETUP ---
    # Normalize empty strings to None immediately
    current_kh_start = kh_start if kh_start else (start if start else None)
    current_kh_end = kh_end if kh_end else (end if end else None)
    current_kh_classes = kh_classes if kh_classes is not None else classes
    current_kh_newcomers = kh_newcomers if kh_newcomers else newcomers

    # Default Logic: Only if BOTH are strictly None
    if current_kh_start is None and current_kh_end is None:
        days_to_monday = today.weekday()
        monday = today - timedelta(days=days_to_monday)
        current_kh_start = monday.strftime('%Y-%m-%d')
        current_kh_end = today.strftime('%Y-%m-%d')

    # --- 2. MONEY CONTEXT SETUP ---
    current_money_start = money_start if money_start else None
    current_money_end = money_end if money_end else None
    
    # Logic for money period: '' means Explicit None (Flat view), None means Default (Week)
    # But Query param might be None if missing.
    # If passed as empty string '', it means "No Grouping".
    
    if money_group_period == "":
        current_money_group = None
    elif money_group_period:
        current_money_group = money_group_period
    elif group_period: # Legacy fallback
        current_money_group = group_period
    else:
         current_money_group = 'day' # Default (User Request)

    current_money_classes = money_classes
    current_money_newcomers = money_newcomers if money_newcomers else None

    # Money Default Dates: Last 7 Days (User Request)
    if current_money_start is None and current_money_end is None:
        start_7days = today - timedelta(days=6)
        current_money_start = start_7days.strftime('%Y-%m-%d')
        current_money_end = today.strftime('%Y-%m-%d')

    # --- HELPER: JOIN DATES (for Newcomers) ---
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute("SELECT role_id, first_seen, user_id FROM players WHERE in_clan = 1")
        join_data = await cursor.fetchall()
        join_dates = {role_id: first_seen for role_id, first_seen, _ in join_data if first_seen}
        
        # Map role_id to user_id for AFK check
        role_user_map = {role_id: user_id for role_id, _, user_id in join_data if user_id}

        # Fetch AFK Users (current AFK from users table)
        cursor = await conn.execute("SELECT id, afk_start, afk_end FROM users WHERE afk_start IS NOT NULL")
        afk_rows = await cursor.fetchall()
        
        # Also fetch from afk_history table for ALL historical AFK periods
        cursor = await conn.execute("SELECT user_id, start_date, end_date FROM afk_history")
        afk_history_rows = await cursor.fetchall()
        
    # Process AFK Data - store as list of periods per user
    afk_map = {}  # {user_id: [(start_dt, end_dt), ...]}
    
    def parse_date(date_val):
        """Parse date from various formats"""
        if not date_val:
            return None
        if isinstance(date_val, datetime):
            return date_val
        try:
            if '.' in str(date_val):
                return datetime.strptime(str(date_val), "%Y-%m-%d %H:%M:%S.%f")
            elif ' ' in str(date_val):
                return datetime.strptime(str(date_val), "%Y-%m-%d %H:%M:%S")
            else:
                return datetime.strptime(str(date_val), "%Y-%m-%d")
        except Exception:
            return None
    
    # Add periods from users table
    for uid, start_ts, end_ts in afk_rows:
        s_dt = parse_date(start_ts)
        e_dt = parse_date(end_ts) or s_dt
        if s_dt and e_dt:
            if uid not in afk_map:
                afk_map[uid] = []
            afk_map[uid].append((s_dt, e_dt))
    
    # Add periods from afk_history table
    for uid, start_ts, end_ts in afk_history_rows:
        s_dt = parse_date(start_ts)
        e_dt = parse_date(end_ts) or s_dt
        if s_dt and e_dt:
            if uid not in afk_map:
                afk_map[uid] = []
            afk_map[uid].append((s_dt, e_dt))

    # --- IMPORT SHARED LOGIC ---
    from logic.helpers import is_newcomer

    def is_newcomer_func(role_id, ref_date_str):
        return is_newcomer(role_id, join_dates, ref_date_str)
        
    def get_afk_dates(role_id):
        if not role_id:
            return None
        uid = role_user_map.get(role_id)
        if not uid:
            return None
        periods = afk_map.get(uid, [])
        if periods:
            # Return the most recent (or current) period
            # Sort by end date descending and take first
            sorted_periods = sorted(periods, key=lambda x: x[1], reverse=True)
            s, e = sorted_periods[0]
            return f"{s.strftime('%d.%m')} - {e.strftime('%d.%m')}"
        return None

    def is_afk_func(role_id):
        if not role_id:
            return False
        uid = role_user_map.get(role_id)
        if not uid:
            return False
        return uid in afk_map

    # --- FETCH & PROCESS KH DATA ---
    kh_rows_raw, kh_s, kh_e, _ = await get_data_from_db(current_kh_start, current_kh_end, None, None, 1)

    # Fallback: If DB returns None/Empty for dates (shouldn't happen), use the calculated defaults
    if not kh_s:
        kh_s = current_kh_start if current_kh_start else date.today().strftime('%Y-%m-%d')
    if not kh_e:
        kh_e = current_kh_end if current_kh_end else date.today().strftime('%Y-%m-%d')

    # --- 3. HISTORY CONTEXT SETUP (Moved here to access kh_s/kh_e) ---
    current_history_start = history_start if history_start else (kh_s if kh_s else None)
    current_history_end = history_end if history_end else (kh_e if kh_e else None)
    current_history_classes = history_classes
    current_history_types = history_types # New filter
    
    # Default logic for history dates if still None (fallback to KH or Today)
    if not current_history_start: current_history_start = current_kh_start
    if not current_history_end: current_history_end = current_kh_end

    # 1. Filter Classes (KH)
    if current_kh_classes:
        kh_rows_filtered = [r for r in kh_rows_raw if r['class_id'] in current_kh_classes]
    else:
        kh_rows_filtered = kh_rows_raw

    # 2. Tiers (Calculated using shared logic)
    kh_active_valors = [r['total_valor'] for r in kh_rows_raw if r['total_valor'] > 0]
    kh_active_gold = [r['total_gold'] for r in kh_rows_raw if r['total_gold'] > 0]
    
    # Calculate Thresholds
    t_v = calculate_thresholds(kh_active_valors)
    t_g = calculate_gold_thresholds(kh_active_gold) # Use specific gold logic
    
    # Sort for rank calculation (required for percentile tiering inside helpers if using rank)
    # The helpers `get_valor_tier` expects sorted list to run bisect.
    kh_active_valors.sort()
    kh_active_gold.sort()

    # Days Diff for Shine
    try:
        d1 = datetime.strptime(kh_s, "%Y-%m-%d")
        d2 = datetime.strptime(kh_e, "%Y-%m-%d")
        days_diff = (d2-d1).days + 1
    except Exception:
        days_diff = 1

    final_kh_rows = []
    for r in kh_rows_filtered:
        row = dict(r)
        row['is_mine'] = (row.get('name', '').lower().strip() in my_nicks)
        row['is_newcomer'] = is_newcomer_func(row.get('role_id'), kh_s)
        row['is_afk'] = is_afk_func(row.get('role_id'))
        row['afk_dates'] = get_afk_dates(row.get('role_id'))
        
        jd = join_dates.get(row.get('role_id'))
        if jd:
            jd_str = jd.split()[0]
            try:
                jd_date = datetime.strptime(jd_str, "%Y-%m-%d")
                diff = (today - jd_date).days
                row['join_date'] = f"{jd_str} ({diff} дн.)"
            except Exception:
                row['join_date'] = jd_str
        else:
            row['join_date'] = ''

        # Newcomer Filter
        if current_kh_newcomers == 'only' and not row['is_newcomer']:
            continue
        if current_kh_newcomers == 'hide' and row['is_newcomer']:
            continue

        # Valor Tier
        row['valor_tier'] = get_valor_tier(row['total_valor'], kh_active_valors, t_v, days_diff)

        # Gold Tier
        row['gold_tier'] = get_gold_tier(row['total_gold'], kh_active_gold, t_g, days_diff)
                
        final_kh_rows.append(row)


    # --- FETCH & PROCESS MONEY DATA ---
    money_rows_raw, m_s, m_e, intervals = await get_data_from_db(
        current_money_start, current_money_end, None, current_money_group, money_group_count
    )


    final_money_rows = []
    
    # Filter Classes (Money)
    if current_money_classes:
        money_rows_filtered = [r for r in money_rows_raw if r['class_id'] in current_money_classes]
    else:
        money_rows_filtered = money_rows_raw
        
    for r in money_rows_filtered:
        row = dict(r)
        row['is_mine'] = (row.get('name', '').lower().strip() in my_nicks)
        row['is_newcomer'] = is_newcomer_func(row.get('role_id'), m_s)
        row['is_afk'] = is_afk_func(row.get('role_id'))
        row['afk_dates'] = get_afk_dates(row.get('role_id'))
        
        jd = join_dates.get(row.get('role_id'))
        if jd:
            jd_str = jd.split()[0]
            try:
                jd_date = datetime.strptime(jd_str, "%Y-%m-%d")
                diff = (today - jd_date).days
                row['join_date'] = f"{jd_str} ({diff} дн.)"
            except Exception:
                row['join_date'] = jd_str
        else:
            row['join_date'] = ''
        
        
        # Newcomer Filter
        if current_money_newcomers == 'only' and not row['is_newcomer']:
            continue
        if current_money_newcomers == 'hide' and row['is_newcomer']:
            continue
        
        # Calculate Interval Flags
        if 'interval_stats' in row:
             # Parse join date for calculation
             jd_dt = None
             if jd:
                 try:
                     jd_dt = datetime.strptime(jd.split()[0], "%Y-%m-%d")
                 except Exception:
                     pass

             # Role -> User for AFK
             uid = role_user_map.get(row.get('role_id'))
             u_afk_periods = afk_map.get(uid, []) if uid else []  # List of (start, end) tuples
             
             for istat in row['interval_stats']:
                 i_s = istat.get('start')
                 i_e = istat.get('end')
                 
                 istat['is_pre_join'] = False
                 istat['is_newcomer_stay'] = False
                 istat['is_afk_stay'] = False
                 
                 if i_s and i_e:
                     # 1. Pre-Join: Interval ends before they joined
                     if jd_dt and i_e.date() < jd_dt.date():
                         istat['is_pre_join'] = True
                     
                     # 2. Newcomer stay: First 7 days
                     # Show turquoise if interval overlaps with [join_date, join_date+7]
                     if jd_dt:
                         nc_end = jd_dt + timedelta(days=6) # 7 days total (0 to 6)
                         # Simple Overlap Check
                         # max(i_s, jd_dt) <= min(i_e, nc_end)
                         # Dates in istat are datetime, jd_dt is datetime
                         overlap_start = max(i_s, jd_dt)
                         overlap_end = min(i_e, timedelta(days=1, seconds=-1) + nc_end) # end of nc day
                         
                         if overlap_start <= overlap_end:
                              istat['is_newcomer_stay'] = True
                     

                     # 3. AFK stay - check against ALL AFK periods
                     for afk_period in u_afk_periods:
                         a_s, a_e = afk_period
                         # Overlap check
                         if max(i_s, a_s) <= min(i_e, a_e):
                             istat['is_afk_stay'] = True
                             break  # Found overlap, no need to check more
        final_money_rows.append(row)


    # --- HISTORY / LAST UPDATED ---

    last_upd = await get_last_update_time()
    
    # History Query Construction
    sql_history = """
        SELECT e.event_date, COALESCE(p.nickname, 'ID '||e.role_id), p.class_id, e.raw_desc, e.event_type, e.role_id, i.name, e.timestamp 
        FROM events e 
        LEFT JOIN players p ON e.role_id = p.role_id 
        LEFT JOIN items i ON (e.event_type = 0 AND e.value = i.id)
        WHERE 1=1
    """
    h_params = []

    # 1. Date Filter
    if current_history_start:
        sql_history += " AND substr(e.event_date, 1, 10) >= ?"
        h_params.append(current_history_start)
    if current_history_end:
        sql_history += " AND substr(e.event_date, 1, 10) <= ?"
        h_params.append(current_history_end)

    # 2. Class Filter (SQL level for efficiency)
    if current_history_classes:
        placeholders = ','.join('?' for _ in current_history_classes)
        sql_history += f" AND p.class_id IN ({placeholders})"
        h_params.extend(current_history_classes)

    # 3. Event Type Filter (SQL)
    if current_history_types:
        # Mapping
        # Valor=1, Gold=2, Items=0, Roster=[6, 8, 10]
        allowed_types = []
        for t in current_history_types:
            if t == 'valor': allowed_types.append(1)
            elif t == 'gold': allowed_types.append(2)
            elif t == 'items': allowed_types.append(0)
            elif t == 'roster': allowed_types.extend([6, 8, 10])
        
        if allowed_types:
            placeholders = ','.join('?' for _ in allowed_types)
            sql_history += f" AND e.event_type IN ({placeholders})"
            h_params.extend(allowed_types)

    sql_history += " ORDER BY e.timestamp DESC LIMIT 500" # Increased limit slightly
    
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(sql_history, tuple(h_params))
        raw_history = await cursor.fetchall()
        
    history_rows = []
    
    # Helper for fast newcomer check context
    h_s_date = current_history_start if current_history_start else date.today().strftime('%Y-%m-%d')

    for date_evt, name, cid, desc, etype, role_id, item_name, timestamp in raw_history:
        icon = f"/static/icons/{cid}.png" if cid in CLASSES else ""
        cname = CLASSES[cid][0] if cid in CLASSES else ""
        is_mine = (name and name.lower().strip() in my_nicks)
        
        history_rows.append((date_evt, name, icon, cname, desc, etype, role_id, is_mine, item_name, timestamp))


    # --- CLASS LISTS ---
    def make_class_list(sel_ids):
        cl = []
        for cid, (cname, _, _) in CLASSES.items():
            cl.append({
                "id": cid, "name": cname, "icon": f"/static/icons/{cid}.png",
                "selected": (cid in sel_ids) if sel_ids else False
            })
        # Sort
        prio = [0, 3, 4, 7, 8, 9]
        cl.sort(key=lambda x: (0, prio.index(x['id'])) if x['id'] in prio else (1, x['id']))
        return cl

    return templates.TemplateResponse("index.html", {
        "request": request,
        "is_authenticated": is_authenticated,
        "is_admin": is_admin, 
        "bot_username": BOT_USERNAME,
        "last_updated": last_upd,
        "user_nickname": user_nickname,
        "user_avatar": user_avatar,
        
        # KH Context
        "kh_rows": final_kh_rows,
        "current_kh_start": kh_s,
        "current_kh_end": kh_e,
        "kh_all_classes": make_class_list(current_kh_classes),
        "kh_newcomers": current_kh_newcomers,
        
        # Money Context
        "money_rows": final_money_rows,
        "current_money_start": m_s,
        "current_money_end": m_e,
        "money_all_classes": make_class_list(current_money_classes),
        "money_newcomers": current_money_newcomers,
        "intervals": intervals,
        "group_period": current_money_group,
        "group_count": money_group_count,
        
        # Other
        "history_rows": history_rows,
        "current_history_start": current_history_start,
        "current_history_end": current_history_end,
        "history_all_classes": make_class_list(current_history_classes),
        "current_history_types": current_history_types,
        "CLASSES": CLASSES # needed?
    })
  except Exception as e:
      return f"Server Error: {str(e)}"

@router.get("/admin/auth", response_class=HTMLResponse)
async def remote_auth_page(request: Request):
    """
    Secret admin page for remote browser authentication.
    """
    # Auth Logic Reuse
    from database import User, session
    user_id = request.session.get('user_id')
    is_admin = False
    
    if user_id:
        u = session.query(User).filter_by(telegram_id=user_id).first()
        if u and u.is_master:
            is_admin = True
            
    return templates.TemplateResponse("remote_auth.html", {"request": request, "is_admin": is_admin})
