import logging
from typing import Any, Dict
from sqlalchemy import select, delete, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import Player, ConstantParty, PartyMember, AsyncSessionLocal

async def get_party(session: AsyncSession, role_id: int) -> Dict[str, Any]:
    """Get party members for a player."""
    try:
        # Find party membership for this player
        stmt = select(PartyMember.party_id, PartyMember.is_leader).where(PartyMember.player_role_id == role_id)
        result = await session.execute(stmt)
        row = result.first()

        if not row:
            return {"status": "ok", "party": None, "members": []}

        party_id, is_leader = row.party_id, row.is_leader

        # Get party name and color
        stmt_party = select(ConstantParty.name, ConstantParty.color).where(ConstantParty.id == party_id)
        result_party = await session.execute(stmt_party)
        party_row = result_party.first()
        party_name = party_row.name if party_row else None
        party_color = party_row.color if party_row else None

        # Get all party members
        stmt_members = (
            select(PartyMember.player_role_id, PartyMember.is_leader, Player.nickname, Player.class_id)
            .join(Player, PartyMember.player_role_id == Player.role_id, isouter=True)
            .where(PartyMember.party_id == party_id)
            .order_by(PartyMember.is_leader.desc(), Player.nickname)
        )
        result_members = await session.execute(stmt_members)
        rows = result_members.all()
        
        members = []
        for m_role_id, m_is_leader, m_nick, m_class_id in rows:
            members.append(
                {
                    "role_id": m_role_id,
                    "nickname": m_nick or f"ID {m_role_id}",
                    "class_id": m_class_id or -1,
                    "is_leader": bool(m_is_leader),
                }
            )

        return {
            "status": "ok",
            "party": {"id": party_id, "name": party_name, "color": party_color, "is_leader": bool(is_leader)},
            "members": members,
        }
    except Exception as e:
        logging.error(f"Error in party_get logic: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def add_to_party(session: AsyncSession, leader_role_id: int, member_nickname: str) -> Dict[str, Any]:
    """Add a player to party. Creates party if needed."""
    try:
        # Find new member by nickname
        stmt_member = select(Player.role_id).where(Player.nickname == member_nickname)
        result_member = await session.execute(stmt_member)
        member_row = result_member.first()

        if not member_row:
            return {"status": "error", "message": f"Игрок '{member_nickname}' не найден"}

        member_role_id = member_row.role_id

        # Find or create party for leader
        stmt_leader = select(PartyMember.party_id).where(PartyMember.player_role_id == leader_role_id)
        result_leader = await session.execute(stmt_leader)
        leader_party = result_leader.first()

        if leader_party:
            party_id = leader_party.party_id
        else:
            # Create new party
            new_party = ConstantParty(name=None)
            session.add(new_party)
            await session.flush()
            party_id = new_party.id
            
            # Add leader as first member
            leader_member = PartyMember(party_id=party_id, player_role_id=leader_role_id, is_leader=True)
            session.add(leader_member)

        # Add new member
        new_member = PartyMember(party_id=party_id, player_role_id=member_role_id, is_leader=False)
        session.add(new_member)
        await session.commit()

        return {"status": "ok", "message": f"Игрок {member_nickname} добавлен в КП"}
    except Exception as e:
        await session.rollback()
        logging.error(f"Error in party_add logic: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def remove_from_party(session: AsyncSession, member_role_id: int) -> Dict[str, Any]:
    """Remove a player from party."""
    try:
        # Get party id before delete
        stmt = select(PartyMember.party_id).where(PartyMember.player_role_id == member_role_id)
        result = await session.execute(stmt)
        row = result.first()

        if not row:
            return {"status": "error", "message": "Игрок не состоит в КП"}

        party_id = row.party_id

        # Remove member
        await session.execute(delete(PartyMember).where(PartyMember.player_role_id == member_role_id))

        # Check if party is empty
        stmt_count = select(func.count()).select_from(PartyMember).where(PartyMember.party_id == party_id)
        result_count = await session.execute(stmt_count)
        count = result_count.scalar()

        if count == 0:
            await session.execute(delete(ConstantParty).where(ConstantParty.id == party_id))

        await session.commit()
        return {"status": "ok"}
    except Exception as e:
        await session.rollback()
        logging.error(f"Error in party_remove logic: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def rename_party(session: AsyncSession, party_id: int, new_name: str) -> Dict[str, Any]:
    """Rename a party."""
    try:
        processed_name = new_name.strip() or None
        await session.execute(update(ConstantParty).where(ConstantParty.id == party_id).values(name=processed_name))
        await session.commit()
        return {"status": "ok"}
    except Exception as e:
        await session.rollback()
        logging.error(f"Error in party_rename logic: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def update_party_color(session: AsyncSession, party_id: int, color: str) -> Dict[str, Any]:
    """Update party color."""
    try:
        processed_color = color.strip() or None
        await session.execute(update(ConstantParty).where(ConstantParty.id == party_id).values(color=processed_color))
        await session.commit()
        return {"status": "ok"}
    except Exception as e:
        await session.rollback()
        logging.error(f"Error in update_party_color logic: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def transfer_leadership(session: AsyncSession, party_id: int, new_leader_role_id: int) -> Dict[str, Any]:
    """Transfer party leadership to another member."""
    try:
        # Check if new leader is in the party
        stmt = select(PartyMember).where(and_(PartyMember.party_id == party_id, PartyMember.player_role_id == new_leader_role_id))
        result = await session.execute(stmt)
        if not result.first():
            return {"status": "error", "message": "Игрок не состоит в этой КП"}

        # Reset current leader(s)
        await session.execute(update(PartyMember).where(PartyMember.party_id == party_id).values(is_leader=False))
        
        # Set new leader
        await session.execute(
            update(PartyMember)
            .where(and_(PartyMember.party_id == party_id, PartyMember.player_role_id == new_leader_role_id))
            .values(is_leader=True)
        )
        await session.commit()
        return {"status": "ok", "message": "Лидерство передано"}
    except Exception as e:
        await session.rollback()
        logging.error(f"Error in transfer_leadership logic: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
