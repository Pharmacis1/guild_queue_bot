import logging
from datetime import datetime
from typing import Any, Dict, Optional

import aiosqlite

import web_database  # Access web_database.DB_NAME at runtime
from consts import CLASSES


# Helper to parse dates safely
def parse_date_safe(date_str: str) -> Optional[str]:
    if not date_str:
        return None
    try:
        # Try ISO format (YYYY-MM-DDTHH:MM:SS)
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        # Fallback for simple date YYYY-MM-DD
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            try:
                # Last resort: dateutil if available (for other formats)
                from dateutil.parser import parse

                dt = parse(date_str)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                logging.error(f"Date parse error: {e}")
                return None


async def update_player_logic(role_id: int, update_data: Dict[str, Any], db_path: str = None) -> Dict[str, Any]:
    """
    Core logic for updating a player's profile.
    Handles:
    - Player fields (nick, class, in_clan, is_alt)
    - User Linking (via Telegram ID)
    - Bot Character Sync (characters table)
    - AFK History updates (users table)
    """

    if db_path is None:
        db_path = web_database.DB_NAME

    nickname = update_data.get("nickname")
    class_id = update_data.get("class_id")
    in_clan = update_data.get("in_clan")
    is_alt = update_data.get("is_alt")
    telegram_id_input = update_data.get("telegram_id")
    afk_start_str = update_data.get("afk_start")
    afk_end_str = update_data.get("afk_end")

    logging.info(f"Logic update_player: {role_id} nick={nickname} tg={telegram_id_input} DB={db_path}")

    async with aiosqlite.connect(db_path) as conn:
        # 1. Current State
        async with conn.execute("SELECT user_id, nickname FROM players WHERE role_id = ?", (role_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise ValueError("Player not found")
            current_user_id, current_nickname = row

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
                    async with conn.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?)", (username,)) as cursor:
                        u_row = await cursor.fetchone()
                        if u_row:
                            new_user_id = u_row[0]
                        else:
                            # Create stub user
                            async with conn.execute("INSERT INTO users (username) VALUES (?)", (username,)) as cursor:
                                new_user_id = cursor.lastrowid
                else:
                    # Search by telegram_id (must be numeric)
                    try:
                        tg_id = int(s_tg)
                        async with conn.execute("SELECT id FROM users WHERE telegram_id = ?", (tg_id,)) as cursor:
                            u_row = await cursor.fetchone()
                            if u_row:
                                new_user_id = u_row[0]
                            else:
                                # Create stub user with telegram_id
                                async with conn.execute("INSERT INTO users (telegram_id) VALUES (?)", (tg_id,)) as cursor:
                                    new_user_id = cursor.lastrowid
                    except ValueError:
                        # NOT a number and NOT @ -> Virtual Group (treat as username)
                        async with conn.execute("SELECT id FROM users WHERE LOWER(username) = LOWER(?)", (s_tg,)) as cursor:
                            u_row = await cursor.fetchone()
                            if u_row:
                                new_user_id = u_row[0]
                            else:
                                # Create virtual user record
                                async with conn.execute("INSERT INTO users (username) VALUES (?)", (s_tg,)) as cursor:
                                    new_user_id = cursor.lastrowid

        # 3. Prepare Updates for Players Table
        updates = []
        params = []

        if nickname is not None:
            cleaned_nick = nickname.strip() if nickname else None
            updates.append("nickname = ?")
            params.append(cleaned_nick)

        if class_id is not None:
            if class_id not in CLASSES and class_id != -1:
                raise ValueError(f"Invalid Class ID: {class_id}")
            updates.append("class_id = ?")
            params.append(class_id)

        if in_clan is not None:
            updates.append("in_clan = ?")
            params.append(1 if in_clan else 0)

        if is_alt is not None:
            updates.append("is_alt = ?")
            params.append(1 if is_alt else 0)

        # Always update user_id (might be unchanged, or set to None/New)
        updates.append("user_id = ?")
        params.append(new_user_id)

        if updates:
            sql = f"UPDATE players SET {', '.join(updates)} WHERE role_id = ?"
            params.append(role_id)
            await conn.execute(sql, tuple(params))

        # 4. SYNC TO BOT TABLES ("characters")
        # Ensure 'characters' table reflects this player if linked to a User

        # Determine target nickname (if changed use new, else old)
        target_nick = nickname.strip() if nickname else current_nickname

        if new_user_id and target_nick:
            # Check existence
            async with conn.execute("SELECT id FROM characters WHERE nickname = ?", (target_nick,)) as cursor:
                char_row = await cursor.fetchone()

            # Logic: If Player says is_alt=True (1), then characters.is_main=False (0)
            # If Player is_alt=False (0) [implies Main], then characters.is_main=True (1)
            # BUT we only have 'is_alt' from update_data if it was passed.
            # If is_alt was NOT passed, we should check DB? Or assume no change?
            # Existing code only updated if passed.
            # But here we need `is_main_val` for the UPDATE command below.

            # We need the final state of is_alt.
            final_is_alt = is_alt
            if final_is_alt is None:
                # Fetch current
                async with conn.execute("SELECT is_alt FROM players WHERE role_id = ?", (role_id,)) as cursor:
                    r = await cursor.fetchone()
                    final_is_alt = bool(r[0]) if r else False

            is_main_val = 0 if final_is_alt else 1

            if char_row:
                await conn.execute(
                    "UPDATE characters SET user_id = ?, is_main = ? WHERE nickname = ?",
                    (new_user_id, is_main_val, target_nick),
                )
            else:
                await conn.execute(
                    "INSERT INTO characters (user_id, nickname, is_main) VALUES (?, ?, ?)",
                    (new_user_id, target_nick, is_main_val),
                )

            # 5. Demotion Logic: If this char is now MAIN, set all other chars of this user to NOT MAIN
            if is_main_val:
                await conn.execute(
                    "UPDATE characters SET is_main = 0 WHERE user_id = ? AND nickname != ?", (new_user_id, target_nick)
                )

        # 6. REFLECT AFK DATES
        logging.info(f"Update Logic: new_user_id={new_user_id}, afk_str={afk_start_str}")
        if new_user_id:
            # Only update if explicit values provided (not None)
            if afk_start_str is not None:  # Can be empty string "" to clear
                start_val = parse_date_safe(afk_start_str)
                logging.info(f"Parsed Start: {start_val}")  # Uses global logger if defined or logging
                # Note: `afk_end` is coupled in the UI usually.
                # If afk_end_str is None (not passed), we might leave it?
                # But existing code updated both if even one was present?
                # unique case: usually they come together.
                # Existing code: `if afk_start_str is not None:` -> updates both.

                end_val = parse_date_safe(afk_end_str)

                await conn.execute(
                    "UPDATE users SET afk_start = ?, afk_end = ? WHERE id = ?", (start_val, end_val, new_user_id)
                )

        await conn.commit()
        return {"status": "ok", "message": "Saved & Synced"}


async def get_player_profile(role_id: int) -> Optional[Dict[str, Any]]:
    """
    Fetches full profile data for the modal.
    """
    async with aiosqlite.connect(web_database.DB_NAME) as conn:
        conn.row_factory = aiosqlite.Row

        # 1. Basic Player & User Info
        sql = """
            SELECT p.role_id, p.nickname, p.class_id, p.in_clan, p.is_alt, 
                   u.id as user_id, u.telegram_id, u.username, u.afk_start, u.afk_end
            FROM players p
            LEFT JOIN users u ON p.user_id = u.id
            WHERE p.role_id = ?
        """
        async with conn.execute(sql, (role_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            
            data = dict(row)

        user_id = data["user_id"]

        # Fallback: if user_id is missing in players, look it up in characters table
        if not user_id and data["nickname"]:
            cursor = await conn.execute("SELECT user_id FROM characters WHERE LOWER(TRIM(nickname)) = LOWER(TRIM(?))", (data["nickname"],))
            c_row = await cursor.fetchone()
            if c_row and c_row["user_id"]:
                user_id = c_row["user_id"]
                data["user_id"] = user_id

        data["afk_history"] = []
        data["queues"] = []
        data["linked_chars"] = []
        data["party"] = None

        # 2. AFK History
        if user_id:
            h_sql = "SELECT id, start_date, end_date, reason FROM afk_history WHERE user_id = ? ORDER BY start_date DESC LIMIT 5"
            h_params = (user_id,)
        else:
            h_sql = "SELECT id, start_date, end_date, reason FROM afk_history WHERE role_id = ? ORDER BY start_date DESC LIMIT 5"
            h_params = (role_id,)

        async with conn.execute(h_sql, h_params) as cursor:
            h_rows = await cursor.fetchall()
            for hr in h_rows:
                data["afk_history"].append({
                    "id": hr["id"],
                    "start": str(hr["start_date"]), 
                    "end": str(hr["end_date"]),
                    "reason": hr["reason"]
                })

        # 3. Active Queues
        if user_id:
            q_sql = """
                SELECT qe.id, qt.name, qe.auto_requeue, qe.character_name
                FROM queue_entries qe
                JOIN queue_types qt ON qe.queue_type_id = qt.id
                WHERE qe.user_id = ?
            """
            async with conn.execute(q_sql, (user_id,)) as cursor:
                q_rows = await cursor.fetchall()
                data["queues"] = [dict(qr) for qr in q_rows]

        # 4. Linked Characters (Twins)
        if user_id:
            c_sql = """
                SELECT c.nickname, c.is_main, MAX(p.class_id) as class_id 
                FROM characters c
                LEFT JOIN players p ON LOWER(TRIM(c.nickname)) = LOWER(TRIM(p.nickname))
                WHERE c.user_id = ?
                GROUP BY c.nickname, c.is_main
            """
            async with conn.execute(c_sql, (user_id,)) as cursor:
                c_rows = await cursor.fetchall()
                for cr in c_rows:
                    data["linked_chars"].append({
                        "nickname": cr["nickname"],
                        "is_main": bool(cr["is_main"]),
                        "class_id": cr["class_id"]
                    })
        
        # Integrity check: ensure current player nickname is in the list
        if data["nickname"]:
            nicks = {c["nickname"] for c in data["linked_chars"]}
            if data["nickname"] not in nicks:
                pass

        # 5. Constant Parties (CP)
        if user_id:
            p_sql = """
                SELECT DISTINCT cp.id, cp.name, cp.color, pm.is_leader 
                FROM party_members pm
                JOIN constant_parties cp ON pm.party_id = cp.id
                WHERE pm.player_role_id IN (
                    SELECT role_id FROM players WHERE user_id = ?
                )
            """
            cp_params = (user_id,)
        else:
            p_sql = """
                SELECT cp.id, cp.name, cp.color, pm.is_leader 
                FROM party_members pm
                JOIN constant_parties cp ON pm.party_id = cp.id
                WHERE pm.player_role_id = ?
            """
            cp_params = (role_id,)

        async with conn.execute(p_sql, cp_params) as cursor:
            p_rows = await cursor.fetchall()
            data["parties"] = []
            
            for pr in p_rows:
                party_data = dict(pr)
                party_id = party_data["id"]
                
                # Fetch members for this party
                m_sql = """
                    SELECT p.nickname, pm.is_leader, p.class_id, p.role_id
                    FROM party_members pm
                    JOIN players p ON pm.player_role_id = p.role_id
                    WHERE pm.party_id = ?
                """
                async with conn.execute(m_sql, (party_id,)) as m_cursor:
                    m_rows = await m_cursor.fetchall()
                    party_data["members"] = [dict(mr) for mr in m_rows]
                
                data["parties"].append(party_data)

        # For backwards compatibility
        data["party"] = data["parties"][0] if data["parties"] else None

        return data
