import logging
from datetime import datetime, timedelta, date, time
from calendar import monthrange
from typing import Any, Dict, Optional
from sqlalchemy import select, update, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import User, Player, Character, AFKHistory, AsyncSessionLocal, ConstantParty, PartyMember, QueueEntry, QueueType, Event, RewardHistory
from consts import CLASSES

# Helper to parse dates safely
def parse_date_safe(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        # Try ISO format (YYYY-MM-DDTHH:MM:SS)
        return datetime.fromisoformat(date_str)
    except ValueError:
        # Fallback for simple date YYYY-MM-DD
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            try:
                # Last resort: dateutil if available (for other formats)
                from dateutil.parser import parse
                return parse(date_str)
            except Exception as e:
                logging.error(f"Date parse error: {e}")
                return None


async def update_player_logic(session: AsyncSession, role_id: int, update_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Core logic for updating a player's profile using AsyncSession.
    """

    nickname = update_data.get("nickname")
    class_id = update_data.get("class_id")
    in_clan = update_data.get("in_clan")
    is_alt = update_data.get("is_alt")
    telegram_id_input = update_data.get("telegram_id")
    afk_start_str = update_data.get("afk_start")
    afk_end_str = update_data.get("afk_end")
    afk_reason = update_data.get("afk_reason")

    logging.info(f"Logic update_player: {role_id} nick={nickname} tg={telegram_id_input}")

    try:
        # 1. Current State
        stmt_player = select(Player).where(Player.role_id == role_id)
        result_player = await session.execute(stmt_player)
        player = result_player.scalar_one_or_none()
        if not player:
            raise ValueError("Player not found")
        
        current_user_id = player.user_id
        current_nickname = player.nickname
        new_user_id = current_user_id

        # 2. Handle User Linking
        if telegram_id_input is not None:
            s_tg = str(telegram_id_input).strip()
            if s_tg == "":
                new_user_id = None
            else:
                if s_tg.startswith("@"):
                    # Search by username (case-insensitive)
                    username = s_tg[1:] # Remove @
                    stmt_user = select(User.id).where(func.lower(User.username) == func.lower(username))
                    result_user = await session.execute(stmt_user)
                    u_row = result_user.first()
                    if u_row:
                        new_user_id = u_row.id
                    else:
                        # Create stub user
                        new_user = User(username=username)
                        session.add(new_user)
                        await session.flush()
                        new_user_id = new_user.id
                else:
                    # Search by telegram_id (must be numeric)
                    try:
                        tg_id = int(s_tg)
                        stmt_user = select(User.id).where(User.telegram_id == tg_id)
                        result_user = await session.execute(stmt_user)
                        u_row = result_user.first()
                        if u_row:
                            new_user_id = u_row.id
                        else:
                            # Create stub user with telegram_id
                            new_user = User(telegram_id=tg_id)
                            session.add(new_user)
                            await session.flush()
                            new_user_id = new_user.id
                    except ValueError:
                        # NOT a number and NOT @ -> Virtual Group (treat as username)
                        stmt_user = select(User.id).where(func.lower(User.username) == func.lower(s_tg))
                        result_user = await session.execute(stmt_user)
                        u_row = result_user.first()
                        if u_row:
                            new_user_id = u_row.id
                        else:
                            # Create virtual user record
                            new_user = User(username=s_tg)
                            session.add(new_user)
                            await session.flush()
                            new_user_id = new_user.id

        # 3. Update Players Table
        if nickname is not None:
            new_nick = nickname.strip()
            if new_nick:  # Only update if not empty to prevent accidental wipe
                player.nickname = new_nick

        if class_id is not None:
            if class_id not in CLASSES and class_id != -1:
                raise ValueError(f"Invalid Class ID: {class_id}")
            player.class_id = class_id

        if in_clan is not None:
            player.in_clan = 1 if in_clan else 0

        if is_alt is not None:
            player.is_alt = 1 if is_alt else 0

        player.user_id = new_user_id

        # 4. SYNC TO BOT TABLES ("characters")
        target_nick = nickname.strip() if nickname else current_nickname

        if new_user_id and target_nick:
            # Check existence in characters table
            stmt_char = select(Character).where(Character.nickname == target_nick)
            result_char = await session.execute(stmt_char)
            char_obj = result_char.scalar_one_or_none()

            is_main_val = 0 if player.is_alt else 1

            if char_obj:
                char_obj.user_id = new_user_id
                char_obj.is_main = bool(is_main_val)
            else:
                new_char = Character(user_id=new_user_id, nickname=target_nick, is_main=bool(is_main_val))
                session.add(new_char)

            # 5. Demotion Logic: If this char is now MAIN, set all other chars of this user to NOT MAIN
            if is_main_val:
                await session.execute(
                    update(Character)
                    .where(and_(Character.user_id == new_user_id, Character.nickname != target_nick))
                    .values(is_main=False)
                )

        # 6. REFLECT AFK DATES
        if "afk_start" in update_data:
            start_val = parse_date_safe(update_data.get("afk_start"))
            end_val = parse_date_safe(update_data.get("afk_end"))
            new_reason = update_data.get("afk_reason")

            # Update Current Status in Users table (if linked)
            if new_user_id:
                await session.execute(
                    update(User)
                    .where(User.id == new_user_id)
                    .values(afk_start=start_val, afk_end=end_val, afk_reason=new_reason)
                )

            # Update Current Status in Players table (always, for unlinked chars)
            player.afk_start = start_val
            player.afk_end = end_val
            player.afk_reason = new_reason
            
            # Log to history table (MSK Time - simple offset for now)
            now_msk = datetime.utcnow() + timedelta(hours=3)
            new_history = AFKHistory(
                user_id=new_user_id,
                role_id=role_id,
                start_date=start_val,
                end_date=end_val,
                reason=new_reason,
                timestamp=now_msk
            )
            session.add(new_history)

        await session.commit()
        return {"status": "ok", "message": "Saved & Synced"}
    except Exception as e:
        await session.rollback()
        logging.error(f"Error in update_player_logic: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
 
async def calculate_calendar_stats(session: AsyncSession, role_id: int, period_type: str, offset: int = 0) -> Dict[str, Any]:
    """
    Calculates KH stats based on calendar boundaries (day, week(Mon-Sun), month)
    with a given offset (0 = current, -1 = previous, etc.) using MSK context.
    Returns dict: start_date, end_date (string ISO), and stats.
    """
    # MSK is UTC + 3
    now_msk = datetime.utcnow() + timedelta(hours=3)
    today_msk = now_msk.date()
    
    start_dt = today_msk
    end_dt = today_msk
    
    if period_type == "day":
        target_date = today_msk + timedelta(days=offset)
        start_dt = target_date
        end_dt = target_date
    elif period_type == "week":
        # Monday is 0
        start_of_current_week = today_msk - timedelta(days=today_msk.weekday())
        target_week_start = start_of_current_week + timedelta(weeks=offset)
        target_week_end = target_week_start + timedelta(days=6)
        start_dt = target_week_start
        end_dt = target_week_end
    elif period_type == "month":
        # Add offset to month (1-indexed)
        total_months = today_msk.year * 12 + (today_msk.month - 1) + offset
        target_year = total_months // 12
        target_month = (total_months % 12) + 1
        
        start_dt = date(target_year, target_month, 1)
        _, last_day = monthrange(target_year, target_month)
        end_dt = date(target_year, target_month, last_day)

    # Convert start/end dates (in MSK context) back to UTC timestamps for DB filtering
    start_dt_msk = datetime.combine(start_dt, time.min)
    start_dt_utc = start_dt_msk - timedelta(hours=3)
    since_ts = start_dt_utc.timestamp()
    
    end_dt_msk = datetime.combine(end_dt, time.max)
    end_dt_utc = end_dt_msk - timedelta(hours=3)
    until_ts = end_dt_utc.timestamp()
    
    stmt = (
        select(Event.value)
        .where(and_(
            Event.role_id == role_id,
            Event.event_type == 1,
            Event.timestamp >= since_ts,
            Event.timestamp <= until_ts
        ))
    )
    result = await session.execute(stmt)
    vals = result.scalars().all()
    
    stats = {
        "s1": 0, "s2": 0, "s3": 0, "s4": 0, "s5": 0, "s6": 0, "s7": 0,
        "adepts": 0, "dances": 0, "total_valor": 0
    }
    
    for v in vals:
        stats["total_valor"] += (v or 0)
        if v == 4: stats["s1"] += 1
        elif v == 6: stats["s2"] += 1
        elif v == 10: stats["s3"] += 1
        elif v == 14: stats["s4"] += 1
        elif v == 24: stats["s5"] += 1
        elif v == 40: stats["s6"] += 1
        elif v == 70: stats["s7"] += 1
        elif v == 7: stats["adepts"] += 1
        elif v in [2, 8]: stats["dances"] += 1
        
    return {
        "start_date": start_dt.isoformat(),
        "end_date": end_dt.isoformat(),
        "stats": stats
    }
 
 
async def calculate_kh_period_stats(session: AsyncSession, role_id: int, days: int) -> Dict[str, Any]:
    """
    Calculates KH stages and total valor for a given period in days.
    """
    # Use MSK-like offset for consistent logic
    now_ts = datetime.utcnow().timestamp()
    since_ts = now_ts - (days * 86400)
    
    stmt = (
        select(Event.value)
        .where(and_(
            Event.role_id == role_id,
            Event.event_type == 1,
            Event.timestamp >= since_ts
        ))
    )
    result = await session.execute(stmt)
    vals = result.scalars().all()
    
    stats = {
        "s1": 0, "s2": 0, "s3": 0, "s4": 0, "s5": 0, "s6": 0, "s7": 0,
        "adepts": 0, "dances": 0, "total_valor": 0
    }
    
    for v in vals:
        stats["total_valor"] += (v or 0)
        if v == 4: stats["s1"] += 1
        elif v == 6: stats["s2"] += 1
        elif v == 10: stats["s3"] += 1
        elif v == 14: stats["s4"] += 1
        elif v == 24: stats["s5"] += 1
        elif v == 40: stats["s6"] += 1
        elif v == 70: stats["s7"] += 1
        elif v == 7: stats["adepts"] += 1
        elif v in [2, 8]: stats["dances"] += 1
        
    return stats
 
 
async def get_player_profile(session: AsyncSession, role_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetches full profile data for the modal using AsyncSession.
    """
    try:
        # 1. Basic Player & User Info
        stmt = (
            select(
                Player.role_id, Player.nickname, Player.class_id, Player.in_clan, Player.is_alt,
                Player.afk_start.label("p_afk_start"), Player.afk_end.label("p_afk_end"), Player.afk_reason.label("p_afk_reason"),
                User.id.label("user_id"), User.telegram_id, User.username, 
                User.afk_start.label("u_afk_start"), User.afk_end.label("u_afk_end"), User.afk_reason.label("u_afk_reason")
            )
            .join(User, Player.user_id == User.id, isouter=True)
            .where(Player.role_id == role_id)
        )
        result = await session.execute(stmt)
        row = result.first()
        if not row:
            return None
        
        data = {
            "role_id": row.role_id,
            "nickname": row.nickname,
            "class_id": row.class_id,
            "in_clan": row.in_clan,
            "is_alt": row.is_alt,
            "user_id": row.user_id,
            "telegram_id": row.telegram_id,
            "username": row.username,
            "afk_start": row.u_afk_start if row.u_afk_start else row.p_afk_start,
            "afk_end": row.u_afk_end if row.u_afk_end else row.p_afk_end,
            "afk_reason": row.u_afk_reason if row.u_afk_reason else row.p_afk_reason
        }

        user_id = data["user_id"]

        # Fallback: if user_id is missing in players, look it up in characters table
        if not user_id and data["nickname"]:
            stmt_c = select(Character.user_id).where(func.lower(func.trim(Character.nickname)) == func.lower(func.trim(data["nickname"])))
            res_c = await session.execute(stmt_c)
            c_row = res_c.first()
            if c_row and c_row.user_id:
                user_id = c_row.user_id
                data["user_id"] = user_id

        data["afk_history"] = []
        data["queues"] = []
        data["linked_chars"] = []
        data["parties"] = []
        data["events"] = []

        # 2. AFK History
        if user_id:
            h_stmt = select(AFKHistory).where(AFKHistory.user_id == user_id).order_by(AFKHistory.start_date.desc()).limit(5)
        else:
            h_stmt = select(AFKHistory).where(AFKHistory.role_id == role_id).order_by(AFKHistory.start_date.desc()).limit(5)

        h_result = await session.execute(h_stmt)
        for hr in h_result.scalars():
            data["afk_history"].append({
                "id": hr.id,
                "start": hr.start_date.strftime("%d.%m.%Y") if hr.start_date else None,
                "end": hr.end_date.strftime("%d.%m.%Y") if hr.end_date else None,
                "reason": hr.reason
            })

        # 3. Active Queues
        if user_id:
            q_stmt = (
                select(QueueEntry.id, QueueType.name, QueueEntry.auto_requeue, QueueEntry.character_name, QueueEntry.position)
                .join(QueueType, QueueEntry.queue_type_id == QueueType.id)
                .where(QueueEntry.user_id == user_id)
            )
            q_result = await session.execute(q_stmt)
            for qid, qname, auto, cname, q_pos in q_result.all():
                # Calculate real position (excluding non-clan members)
                pos_stmt = (
                    select(func.count(QueueEntry.id))
                    .join(Player, func.lower(func.trim(QueueEntry.character_name)) == func.lower(func.trim(Player.nickname)))
                    .where(
                        QueueEntry.queue_type_id == (select(QueueEntry.queue_type_id).where(QueueEntry.id == qid).scalar_subquery()),
                        QueueEntry.position < q_pos,
                        Player.in_clan == 1
                    )
                )
                real_pos = (await session.execute(pos_stmt)).scalar() or 0
                
                data["queues"].append({
                    "id": qid,
                    "name": qname,
                    "auto_requeue": auto,
                    "character_name": cname,
                    "position": real_pos + 1
                })

        # 4. Linked Characters (Twins)
        if user_id:
            c_stmt = (
                select(Character.nickname, Character.is_main, func.max(Player.class_id).label("class_id"), func.max(Player.role_id).label("role_id"))
                .join(Player, func.lower(func.trim(Character.nickname)) == func.lower(func.trim(Player.nickname)), isouter=True)
                .where(Character.user_id == user_id)
                .group_by(Character.nickname, Character.is_main)
            )
            c_result = await session.execute(c_stmt)
            for cn, ism, cid, rid in c_result.all():
                char_info = {
                    "nickname": cn,
                    "is_main": bool(ism),
                    "class_id": cid,
                    "role_id": rid
                }
                if rid:
                    char_info["kh_stats"] = {
                        "day": await calculate_kh_period_stats(session, rid, 1),
                        "week": await calculate_kh_period_stats(session, rid, 7),
                        "month": await calculate_kh_period_stats(session, rid, 30)
                    }
                data["linked_chars"].append(char_info)

        # 5. Constant Parties (CP)
        if user_id:
            p_stmt = (
                select(ConstantParty.id, ConstantParty.name, ConstantParty.color, PartyMember.is_leader)
                .distinct()
                .join(PartyMember, ConstantParty.id == PartyMember.party_id)
                .where(PartyMember.player_role_id.in_(
                    select(Player.role_id).where(Player.user_id == user_id)
                ))
            )
        else:
            p_stmt = (
                select(ConstantParty.id, ConstantParty.name, ConstantParty.color, PartyMember.is_leader)
                .join(PartyMember, ConstantParty.id == PartyMember.party_id)
                .where(PartyMember.player_role_id == role_id)
            )
        
        p_result = await session.execute(p_stmt)
        for pid, pname, pcolor, is_lead in p_result.all():
            party_data = {
                "id": pid,
                "name": pname,
                "color": pcolor,
                "is_leader": is_lead,
                "members": []
            }
            # Fetch members
            m_stmt = (
                select(Player.nickname, PartyMember.is_leader, Player.class_id, Player.role_id)
                .join(PartyMember, Player.role_id == PartyMember.player_role_id)
                .where(PartyMember.party_id == pid)
            )
            m_result = await session.execute(m_stmt)
            for m_nick, m_lead, m_class, m_role in m_result.all():
                party_data["members"].append({
                    "nickname": m_nick,
                    "is_leader": m_lead,
                    "class_id": m_class,
                    "role_id": m_role
                })
            data["parties"].append(party_data)

        data["party"] = data["parties"][0] if data["parties"] else None
        
        # 6. Recent Events (Valor etc.)
        e_stmt = select(Event).filter_by(role_id=role_id).order_by(Event.timestamp.desc()).limit(20)
        e_result = await session.execute(e_stmt)
        for er in e_result.scalars():
            ts_dt = datetime.fromtimestamp(er.timestamp) if er.timestamp else None
            data["events"].append({
                "id": er.id,
                "timestamp": int(er.timestamp or 0),
                "date": ts_dt.strftime("%Y-%m-%d %H:%M") if ts_dt else "",
                "type": er.event_type or 0,
                "value": er.value or 0,
                "description": er.raw_desc
            })

        # 7. KH Stats Summary
        data["kh_stats"] = {
            "day": await calculate_kh_period_stats(session, role_id, 1),
            "week": await calculate_kh_period_stats(session, role_id, 7),
            "month": await calculate_kh_period_stats(session, role_id, 30)
        }

        # 8. Reward History
        data["reward_history"] = []
        if user_id:
            rh_stmt = (
                select(RewardHistory)
                .where(RewardHistory.user_id == user_id)
                .order_by(RewardHistory.timestamp.desc())
                .limit(50)
            )
            rh_result = await session.execute(rh_stmt)
            for rh in rh_result.scalars():
                data["reward_history"].append({
                    "id": rh.id,
                    "character_name": rh.character_name,
                    "queue_name": rh.queue_name,
                    "issued_by": rh.issued_by,
                    "record_type": rh.record_type,
                    "timestamp": rh.timestamp.strftime("%Y-%m-%d %H:%M") if rh.timestamp else ""
                })

        return data

    except Exception as e:
        logging.error(f"Error in get_player_profile: {e}", exc_info=True)
        return None
