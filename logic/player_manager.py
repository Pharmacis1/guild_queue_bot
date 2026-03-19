import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from sqlalchemy import select, update, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import User, Player, Character, AFKHistory, AsyncSessionLocal, ConstantParty, PartyMember, QueueEntry, QueueType
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
            player.nickname = nickname.strip() if nickname else None

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


async def get_player_profile(session: AsyncSession, role_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetches full profile data for the modal using AsyncSession.
    """
    try:
        # 1. Basic Player & User Info
        stmt = (
            select(
                Player.role_id, Player.nickname, Player.class_id, Player.in_clan, Player.is_alt,
                User.id.label("user_id"), User.telegram_id, User.username, 
                User.afk_start, User.afk_end, User.afk_reason
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
            "afk_start": row.afk_start,
            "afk_end": row.afk_end,
            "afk_reason": row.afk_reason
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

        # 2. AFK History
        if user_id:
            h_stmt = select(AFKHistory).where(AFKHistory.user_id == user_id).order_by(AFKHistory.start_date.desc()).limit(5)
        else:
            h_stmt = select(AFKHistory).where(AFKHistory.role_id == role_id).order_by(AFKHistory.start_date.desc()).limit(5)

        h_result = await session.execute(h_stmt)
        for hr in h_result.scalars():
            data["afk_history"].append({
                "id": hr.id,
                "start": hr.start_date.isoformat() if hr.start_date else None,
                "end": hr.end_date.isoformat() if hr.end_date else None,
                "reason": hr.reason
            })

        # 3. Active Queues
        if user_id:
            q_stmt = (
                select(QueueEntry.id, QueueType.name, QueueEntry.auto_requeue, QueueEntry.character_name)
                .join(QueueType, QueueEntry.queue_type_id == QueueType.id)
                .where(QueueEntry.user_id == user_id)
            )
            q_result = await session.execute(q_stmt)
            for qid, qname, auto, cname in q_result.all():
                data["queues"].append({
                    "id": qid,
                    "name": qname,
                    "auto_requeue": auto,
                    "character_name": cname
                })

        # 4. Linked Characters (Twins)
        if user_id:
            c_stmt = (
                select(Character.nickname, Character.is_main, func.max(Player.class_id).label("class_id"))
                .join(Player, func.lower(func.trim(Character.nickname)) == func.lower(func.trim(Player.nickname)), isouter=True)
                .where(Character.user_id == user_id)
                .group_by(Character.nickname, Character.is_main)
            )
            c_result = await session.execute(c_stmt)
            for cn, ism, cid in c_result.all():
                data["linked_chars"].append({
                    "nickname": cn,
                    "is_main": bool(ism),
                    "class_id": cid
                })

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
        return data

    except Exception as e:
        logging.error(f"Error in get_player_profile: {e}", exc_info=True)
        return None
