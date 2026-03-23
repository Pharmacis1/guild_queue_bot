import logging
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import select, func, and_, String

from consts import CLASSES
from database import AsyncSessionLocal, Event, Player, Character, ConstantParty, PartyMember, User

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

        if period == "day":
            interval_end = current + timedelta(days=count - 1)
            next_start = interval_end + timedelta(days=1)
            label = interval_start.strftime("%d.%m")

        elif period == "week":
            # Logic: Align to real week chunks
            days_to_sunday = 6 - current.weekday()
            interval_end = current + timedelta(days=days_to_sunday)

            if count > 1:
                interval_end += timedelta(weeks=count - 1)

            next_start = interval_end + timedelta(days=1)

            # Cap at e_date
            if interval_end > e_date:
                interval_end = e_date

            label = f"{interval_start.strftime('%d.%m')} - {interval_end.strftime('%d.%m')}"

        elif period == "month":
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

        elif period == "year":
            interval_end = current.replace(month=12, day=31)
            next_start = interval_end + timedelta(days=1)

            if interval_end > e_date:
                interval_end = e_date

            label = interval_start.strftime("%Y")

        else:
            break

        intervals.append({"label": label, "start": interval_start, "end": interval_end})

        current = next_start

    return intervals


async def get_last_update_time():
    """Gets the date of the freshest record in DB and converts to MSK (UTC+3)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.max(Event.timestamp)))
        ts = result.scalar()
        if ts:
            # 1. Get date as UTC
            dt_utc = datetime.fromtimestamp(ts, timezone.utc)
            # 2. Add exactly 3 hours (MSK)
            dt_msk = dt_utc + timedelta(hours=3)
            return dt_msk.strftime("%d.%m.%Y %H:%M") + " (МСК)"
    return "Нет данных"


def analyze_stats(events):
    """
    Analyzes player event list.
    Returns a dictionary with all counters and details for tooltips.
    """
    stats = {
        "s1": 0, "s2": 0, "s3": 0, "s4": 0, "s5": 0, "s6": 0, "s7": 0,
        "adepts": 0, "dances": 0, "total_gold": 0, "total_valor": 0,
        "s1_details": [], "s2_details": [], "s3_details": [], "s4_details": [],
        "s5_details": [], "s6_details": [], "s7_details": [], "valor_details": [],
        "adepts_details": [], "dances_details": []
    }

    events.sort(key=lambda x: x[0])

    # Russian short days
    DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    def fmt_date_rich(ts):
        if not ts: return ""
        dt = datetime.fromtimestamp(ts, timezone(timedelta(hours=3)))
        d_str = dt.strftime("%d.%m")
        t_str = dt.strftime("%H:%M")
        wd = DAYS_RU[dt.weekday()]
        return f"{d_str} {t_str} ({wd})"

    for i, (ts, val, etype) in enumerate(events):
        d_str_rich = fmt_date_rich(ts)

        # Gold
        if etype == 2:
            stats["total_gold"] += val
            continue

        # Valor
        if etype == 1:
            stats["total_valor"] += val
            
            detail_label = ""
            # Stages
            if val == 4:
                is_dance = False
                # Check backward (< 20 min)
                if i > 0:
                    prev_ts, prev_val, prev_type = events[i - 1]
                    if prev_type == 1 and prev_val == 2 and (ts - prev_ts) < 1200:
                        is_dance = True

                # Check forward (< 20 min)
                if not is_dance and i < len(events) - 1:
                    next_ts, next_val, next_type = events[i + 1]
                    if next_type == 1 and next_val == 8 and (next_ts - ts) < 1200:
                        is_dance = True

                if is_dance:
                    stats["dances"] += 1
                    stats["dances_details"].append(f"{d_str_rich} +{val}")
                    detail_label = f"Танцы (4)"
                else:
                    stats["s1"] += 1
                    stats["s1_details"].append(f"{d_str_rich} +{val}")
                    detail_label = f"Этап I (4)"

            elif val == 6:
                stats["s2"] += 1
                stats["s2_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Этап II (6)"
            elif val == 10:
                stats["s3"] += 1
                stats["s3_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Этап III (10)"
            elif val == 14:
                stats["s4"] += 1
                stats["s4_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Этап IV (14)"
            elif val == 24:
                stats["s5"] += 1
                stats["s5_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Этап V (24)"
            elif val == 40:
                stats["s6"] += 1
                stats["s6_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Этап VI (40)"
            elif val == 70:
                stats["s7"] += 1
                stats["s7_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Этап VII (70)"
            elif val == 7:
                stats["adepts"] += 1
                stats["adepts_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Адепты (7)"
            elif val in [2, 8]:
                stats["dances"] += 1
                stats["dances_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Танцы ({val})"
            else:
                detail_label = f"Доблесть ({val})"
            
            if detail_label:
                stats["valor_details"].append(f"{d_str_rich}: {detail_label}")

    return stats


async def get_data_from_db(
    start_date: str = None,
    end_date: str = None,
    classes: List[int] = None,
    group_period: str = None,
    group_count: int = 1,
):
    today = datetime.now()
    if not end_date:
        end_date = today.strftime("%Y-%m-%d")

    # Auto-select: Monday of current week
    if not start_date:
        days_to_subtract = today.weekday()
        monday = today - timedelta(days=days_to_subtract)
        start_date = monday.strftime("%Y-%m-%d")

    # Calculate intervals if grouping is requested
    intervals = []
    if group_period:
        intervals = get_intervals(start_date, end_date, group_period, group_count)

    async with AsyncSessionLocal() as session:
        # Base Query using SQLAlchemy ORM
        stmt = (
            select(
                Player.role_id,
                func.coalesce(Player.nickname, "ID " + func.cast(Player.role_id, String)).label("nickname"),
                Player.class_id,
                Event.timestamp,
                Event.value,
                Event.event_type,
                func.coalesce(Player.user_id, Character.user_id).label("user_id"),
                Player.is_alt,
                ConstantParty.id.label("cp_id"),
                ConstantParty.color.label("cp_color")
            )
            .join(Character, Player.nickname == Character.nickname, isouter=True)
            .join(
                Event,
                and_(
                    Player.role_id == Event.role_id,
                    Event.event_type.in_([1, 2]),
                    func.substr(Event.event_date, 1, 10) >= start_date,
                    func.substr(Event.event_date, 1, 10) <= end_date
                ),
                isouter=True
            )
            .join(PartyMember, Player.role_id == PartyMember.player_role_id, isouter=True)
            .join(ConstantParty, PartyMember.party_id == ConstantParty.id, isouter=True)
            .where(Player.in_clan == 1)
        )

        # Filter by classes
        if classes:
            stmt = stmt.where(Player.class_id.in_(classes))

        result = await session.execute(stmt)
        raw_rows = result.all()

    # Grouping
    players_events = {}
    for rid, name, cid, ts, val, etype, uid, is_alt, cp_id, cp_color in raw_rows:
        if rid not in players_events:
            players_events[rid] = {
                "name": name, 
                "class_id": cid, 
                "user_id": uid,
                "is_alt": bool(is_alt),
                "cp_id": cp_id,
                "cp_color": cp_color,
                "events": []
            }
        players_events[rid]["events"].append((ts, val, etype))

    result = []
    for rid, data in players_events.items():
        # Global stats (Total)
        stats = analyze_stats(data["events"])
        stats["name"] = data["name"]
        stats["role_id"] = rid
        stats["class_id"] = data["class_id"]
        stats["user_id"] = data["user_id"]
        stats["is_alt"] = data["is_alt"]
        stats["cp_id"] = data["cp_id"]
        stats["cp_color"] = data["cp_color"]

        # Calculate stats for each interval
        if intervals:
            stats["interval_stats"] = []
            for interval in intervals:
                # TS alignment with MSK
                msk_offset = timedelta(hours=3)
                tz_msk = timezone(msk_offset)

                dt_start_msk = interval["start"].replace(tzinfo=tz_msk)
                dt_end_msk = (interval["end"] + timedelta(days=1)).replace(tzinfo=tz_msk)

                ts_start = dt_start_msk.timestamp()
                ts_end = dt_end_msk.timestamp()

                interval_events = [ev for ev in data["events"] if ev[0] is not None and ts_start <= ev[0] < ts_end]

                istats = analyze_stats(interval_events)
                stats["interval_stats"].append(
                    {
                        "label": interval["label"],
                        "start": interval["start"],
                        "end": interval["end"],
                        "valor": istats["total_valor"],
                        "gold": istats["total_gold"],
                        "valor_details": istats["valor_details"],
                        "s1": istats["s1"],
                        "s2": istats["s2"],
                        "s3": istats["s3"],
                        "s4": istats["s4"],
                        "s5": istats["s5"],
                        "s6": istats["s6"],
                        "s7": istats["s7"],
                        "adepts": istats["adepts"],
                        "dances": istats["dances"],
                    }
                )

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
    result.sort(key=lambda x: (x.get("s7", 0), x.get("total_valor", 0)), reverse=True)

    # Return intervals too so frontend can build headers
    return result, start_date, end_date, intervals
