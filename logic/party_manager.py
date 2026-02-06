import logging
from typing import Any, Dict

import aiosqlite

import web_database


async def get_party(role_id: int) -> Dict[str, Any]:
    """Get party members for a player."""
    try:
        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            # Find party membership for this player
            async with conn.execute("""
                SELECT pm.party_id, pm.is_leader
                FROM party_members pm
                WHERE pm.player_role_id = ?
            """, (role_id,)) as cursor:
                row = await cursor.fetchone()
            
            if not row:
                return {"status": "ok", "party": None, "members": []}
            
            party_id, is_leader = row
            
            # Get party name
            async with conn.execute("SELECT name FROM constant_parties WHERE id = ?", (party_id,)) as cursor:
                party_row = await cursor.fetchone()
                party_name = party_row[0] if party_row and party_row[0] else None
            
            # Get all party members
            members = []
            async with conn.execute("""
                SELECT pm.player_role_id, pm.is_leader, p.nickname, p.class_id
                FROM party_members pm
                LEFT JOIN players p ON pm.player_role_id = p.role_id
                WHERE pm.party_id = ?
                ORDER BY pm.is_leader DESC, p.nickname
            """, (party_id,)) as cursor:
                rows = await cursor.fetchall()
                for m_role_id, m_is_leader, m_nick, m_class_id in rows:
                    members.append({
                        "role_id": m_role_id,
                        "nickname": m_nick or f"ID {m_role_id}",
                        "class_id": m_class_id or -1,
                        "is_leader": bool(m_is_leader)
                    })
            
            return {
                "status": "ok", 
                "party": {"id": party_id, "name": party_name, "is_leader": bool(is_leader)},
                "members": members
            }
    except Exception as e:
        logging.error(f"Error in party_get logic: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

async def add_to_party(leader_role_id: int, member_nickname: str) -> Dict[str, Any]:
    """Add a player to party. Creates party if needed."""
    try:
        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            # Find new member by nickname
            async with conn.execute("SELECT role_id FROM players WHERE nickname = ?", (member_nickname,)) as cursor:
                member_row = await cursor.fetchone()
            
            if not member_row:
                return {"status": "error", "message": f"Игрок '{member_nickname}' не найден"}
            
            member_role_id = member_row[0]
            
            # Check if member already in a party
            async with conn.execute("SELECT party_id FROM party_members WHERE player_role_id = ?", (member_role_id,)) as cursor:
                existing = await cursor.fetchone()
                if existing:
                    return {"status": "error", "message": "Игрок уже состоит в другой КП"}
            
            # Find or create party for leader
            async with conn.execute(
                "SELECT party_id FROM party_members WHERE player_role_id = ?", 
                (leader_role_id,)
            ) as cursor:
                leader_party = await cursor.fetchone()
            
            if leader_party:
                party_id = leader_party[0]
            else:
                # Create new party with leader
                await conn.execute("INSERT INTO constant_parties (name) VALUES (NULL)")
                async with conn.execute("SELECT last_insert_rowid()") as cursor:
                    party_id = (await cursor.fetchone())[0]
                # Add leader as first member
                await conn.execute(
                    "INSERT INTO party_members (party_id, player_role_id, is_leader) VALUES (?, ?, 1)",
                    (party_id, leader_role_id)
                )
            
            # Add new member
            await conn.execute(
                "INSERT INTO party_members (party_id, player_role_id, is_leader) VALUES (?, ?, 0)",
                (party_id, member_role_id)
            )
            await conn.commit()
            
        return {"status": "ok", "message": f"Игрок {member_nickname} добавлен в КП"}
    except Exception as e:
        logging.error(f"Error in party_add logic: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

async def remove_from_party(member_role_id: int) -> Dict[str, Any]:
    """Remove a player from party."""
    try:
        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            # Get party id before delete
            async with conn.execute("SELECT party_id FROM party_members WHERE player_role_id = ?", (member_role_id,)) as cursor:
                row = await cursor.fetchone()
            
            if not row:
                return {"status": "error", "message": "Игрок не состоит в КП"}
            
            party_id = row[0]
            
            # Remove member
            await conn.execute("DELETE FROM party_members WHERE player_role_id = ?", (member_role_id,))
            
            # Check if party is empty or has only 1 member left - delete party
            # Wait, original logic logic:
            # "Check if party is empty or has only 1 member left" -> wait, if 1 member left, it's just the leader alone?
            # Original code:
            # async with conn.execute("SELECT COUNT(*) FROM party_members WHERE party_id = ?", (party_id,)) as cursor:
            #     count = (await cursor.fetchone())[0]
            # if count == 0: await conn.execute("DELETE FROM constant_parties WHERE id = ?", (party_id,))
            
            # Wait, if I delete the member, count will decrease.
            # If count becomes 0, delete party.
            # If count becomes 1, do we delete? Original code ONLY checked `if count == 0`.
            # But the comment said "or has only 1 member left".
            # Let's stick to the CODE behavior: `if count == 0`.
            
            async with conn.execute("SELECT COUNT(*) FROM party_members WHERE party_id = ?", (party_id,)) as cursor:
                count = (await cursor.fetchone())[0]
            
            if count == 0:
                await conn.execute("DELETE FROM constant_parties WHERE id = ?", (party_id,))
            
            await conn.commit()
            
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Error in party_remove logic: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

async def rename_party(party_id: int, new_name: str) -> Dict[str, Any]:
    """Rename a party."""
    try:
        processed_name = new_name.strip() or None
        
        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            await conn.execute("UPDATE constant_parties SET name = ? WHERE id = ?", (processed_name, party_id))
            await conn.commit()
            
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Error in party_rename logic: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
