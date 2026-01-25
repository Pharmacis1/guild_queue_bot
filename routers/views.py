from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import List
import aiosqlite
import os
from web_database import DB_NAME, get_data_from_db, get_last_update_time
from consts import CLASSES
import bisect
from datetime import datetime, timedelta

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
    # --- AUTH CHECK RESTORED ---
    from database import session, User
    
    # Default values for public access (Guest Mode)
    user_id = request.session.get('user_id')
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
            
            # Load characters for highlighting
            my_nicks = {c.nickname.lower().strip() for c in u.characters if c.nickname}
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
         current_money_group = 'week' # Default

    current_money_classes = money_classes
    current_money_newcomers = money_newcomers if money_newcomers else None

    # Money Default Dates: Last 4 Weeks
    if current_money_start is None and current_money_end is None:
        days_to_monday = today.weekday()
        monday = today - timedelta(days=days_to_monday)
        start_4weeks = monday - timedelta(weeks=3)
        current_money_start = start_4weeks.strftime('%Y-%m-%d')
        current_money_end = today.strftime('%Y-%m-%d')

    # --- HELPER: JOIN DATES (for Newcomers) ---
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute("SELECT role_id, first_seen FROM players WHERE in_clan = 1")
        join_data = await cursor.fetchall()
        join_dates = {role_id: first_seen for role_id, first_seen in join_data if first_seen}

    def is_newcomer_func(role_id, ref_date_str):
        if not role_id or role_id not in join_dates: return False
        try:
            val = join_dates[role_id]
            # Handle "YYYY-MM-DD HH:MM:SS"
            if ' ' in val: val = val.split()[0]
            join_dt = datetime.strptime(val, "%Y-%m-%d")
            ref_dt = datetime.strptime(ref_date_str, "%Y-%m-%d")
            ref_monday = ref_dt - timedelta(days=ref_dt.weekday())
            return (ref_monday - join_dt).days < 7
        except: return False

    # --- FETCH & PROCESS KH DATA ---
    kh_rows_raw, kh_s, kh_e, _ = await get_data_from_db(current_kh_start, current_kh_end, None, None, 1)

    # Fallback: If DB returns None/Empty for dates (shouldn't happen), use the calculated defaults
    if not kh_s: kh_s = current_kh_start if current_kh_start else date.today().strftime('%Y-%m-%d')
    if not kh_e: kh_e = current_kh_end if current_kh_end else date.today().strftime('%Y-%m-%d')

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

    # 2. Tiers (Calculated on GLOBAL rows to preserve ranking context)
    kh_active_valors = sorted([r['total_valor'] for r in kh_rows_raw if r['total_valor'] > 0])
    kh_active_gold = sorted([r['total_gold'] for r in kh_rows_raw if r['total_gold'] > 0])
    
    total_active = len(kh_active_valors)
    total_active_gold = len(kh_active_gold)
    
    import math
    import bisect
    
    # Valor Thresholds
    t_v_gold = 999999
    t_v_silver = 999999
    t_v_10 = 999999
    if total_active > 0:
        t_v_gold = kh_active_valors[max(0, math.ceil(total_active*0.95)-1)]
        t_v_silver = kh_active_valors[max(0, math.ceil(total_active*0.85)-1)]
        t_v_10 = kh_active_valors[-10] if total_active >= 10 else kh_active_valors[0]
        
    # Gold Thresholds
    t_g_10 = 999999999
    if total_active_gold > 0:
        t_g_10 = kh_active_gold[-10] if total_active_gold >= 10 else kh_active_gold[-max(1, total_active_gold//2)]

    # Days Diff for Shine
    try:
        d1 = datetime.strptime(kh_s, "%Y-%m-%d")
        d2 = datetime.strptime(kh_e, "%Y-%m-%d")
        days_diff = (d2-d1).days + 1
    except: days_diff = 1

    final_kh_rows = []
    for r in kh_rows_filtered:
        row = dict(r)
        row['is_mine'] = (row.get('name', '').lower().strip() in my_nicks)
        row['is_newcomer'] = is_newcomer_func(row.get('role_id'), kh_s)

        # Newcomer Filter
        if current_kh_newcomers == 'only' and not row['is_newcomer']: continue
        if current_kh_newcomers == 'hide' and row['is_newcomer']: continue

        # Valor Tier
        val = row['total_valor']
        if val == 0: row['valor_tier'] = 0
        else:
            if val >= t_v_10: row['valor_tier'] = 6 if days_diff >=4 else 7
            else:
                rank = bisect.bisect_right(kh_active_valors, val)
                pct = rank / total_active
                if pct > 0.8: row['valor_tier'] = 5 if days_diff >=4 else 7
                elif pct > 0.6: row['valor_tier'] = 4
                elif pct > 0.4: row['valor_tier'] = 3
                elif pct > 0.2: row['valor_tier'] = 2
                else: row['valor_tier'] = 1

        # Gold Tier
        val_g = row['total_gold']
        if val_g == 0: row['gold_tier'] = 0
        else:
            if val_g >= t_g_10: row['gold_tier'] = 6 if days_diff >=4 else 7
            else:
                rank = bisect.bisect_right(kh_active_gold, val_g)
                pct = rank / total_active_gold
                if pct > 0.8: row['gold_tier'] = 5 if days_diff >=4 else 7
                elif pct > 0.6: row['gold_tier'] = 4
                elif pct > 0.4: row['gold_tier'] = 3
                elif pct > 0.2: row['gold_tier'] = 2
                else: row['gold_tier'] = 1
                
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
        
        # Newcomer Filter
        if current_money_newcomers == 'only' and not row['is_newcomer']: continue
        if current_money_newcomers == 'hide' and row['is_newcomer']: continue
        
        final_money_rows.append(row)


    # --- HISTORY / LAST UPDATED ---
    last_upd = await get_last_update_time()
    
    # History Query Construction
    sql_history = """
        SELECT e.event_date, COALESCE(p.nickname, 'ID '||e.role_id), p.class_id, e.raw_desc, e.event_type, e.role_id, i.name 
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

    for date_evt, name, cid, desc, etype, role_id, item_name in raw_history:
        icon = f"/static/icons/{cid}.png" if cid in CLASSES else ""
        cname = CLASSES[cid][0] if cid in CLASSES else ""
        is_mine = (name and name.lower().strip() in my_nicks)
        
        history_rows.append((date_evt, name, icon, cname, desc, etype, role_id, is_mine, item_name))


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

@router.get("/admin/auth", response_class=HTMLResponse)
async def remote_auth_page(request: Request):
    """
    Secret admin page for remote browser authentication.
    """
    # Auth Logic Reuse
    from database import session, User
    user_id = request.session.get('user_id')
    is_admin = False
    
    if user_id:
        u = session.query(User).filter_by(telegram_id=user_id).first()
        if u and u.is_master:
            is_admin = True
            
    return templates.TemplateResponse("remote_auth.html", {"request": request, "is_admin": is_admin})
