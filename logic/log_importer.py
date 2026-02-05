import logging
from typing import Any, Dict, Set, Tuple

import aiosqlite

import web_database

# Try to import dependencies
try:
    from scripts.board_parser import parse_board_file
except ImportError:
    logging.warning("Could not import board_parser from scripts.board_parser")
    parse_board_file = None

async def process_log_upload(file_path: str) -> Tuple[Dict[str, Any], Set[int], bool]:
    """
    Process the uploaded log file.
    Returns:
        - status_dict: Result of the operation (status, new_events, etc.)
        - missing_item_ids: Set of item IDs that need scraping
        - should_run_pwobs: Boolean indicating if pwobs scraper should be triggered
    """
    if not parse_board_file:
        return {"status": "error", "message": "Parser module missing"}, set(), False

    try:
        # 1. Parse
        data = parse_board_file(file_path)
        if not data:
            return {"status": "error", "message": "File empty or data too old"}, set(), False
            
        new_events = 0
        item_ids = set()

        # 2. Write to DB
        async with aiosqlite.connect(web_database.DB_NAME) as conn:
            cursor = await conn.cursor()
            
            # Pre-fetch known nicknames for description replacement
            # We collect all IDs mentioned in descriptions or acting
            all_involved_ids = set()
            for row in data:
                all_involved_ids.add(row['role_id'])
                if row['raw_params']:
                    try:
                        p0 = int(row['raw_params'].split(',')[0])
                        all_involved_ids.add(p0)
                    except: pass
            
            # Fetch existing nicknames
            id_to_nick = {}
            if all_involved_ids:
                q_placeholders = ','.join(['?'] * len(all_involved_ids))
                async with conn.execute(f"SELECT role_id, nickname FROM players WHERE role_id IN ({q_placeholders})", list(all_involved_ids)) as fetch_cursor:
                    rows = await fetch_cursor.fetchall()
                    for r_id, r_nick in rows:
                        if r_nick:
                            id_to_nick[r_id] = r_nick

            for row in data:
                rid = row['role_id']
                
                # [FIX] Filter invalid IDs (like ID 1)
                if rid < 16:
                    continue

                etype = row['action_type']
                desc = row['description']
                
                val = 0
                target_id = None
                
                if row['raw_params']:
                    try:
                        val = int(row['raw_params'].split(',')[0])
                        target_id = val # p0 is often the target
                        if etype == 0: # Item event
                            item_ids.add(val)
                    except: pass

                # [FIX] Resolve ID in description
                if target_id and f"ID {target_id}" in desc:
                   t_nick = id_to_nick.get(target_id)
                   if t_nick:
                       desc = desc.replace(f"ID {target_id}", f"{t_nick}")

                # Ensure actor exists
                await cursor.execute("INSERT OR IGNORE INTO players (role_id, in_clan) VALUES (?, 1)", (rid,))
                
                # [FIX] Status Updates
                is_leave_self = (etype == 8) # Покинул гильдию
                is_kick = (etype == 10)      # Изгнал ID ...
                is_join = (etype == 6)       # Вступил
                
                if is_leave_self:
                    # Actor left
                    await cursor.execute("UPDATE players SET in_clan = 0 WHERE role_id = ?", (rid,))
                
                elif is_kick:
                    # Actor KICKED someone. The TARGET (val) left.
                    # Ensure target exists in DB first
                    if target_id:
                        await cursor.execute("INSERT OR IGNORE INTO players (role_id, in_clan) VALUES (?, 1)", (target_id,))
                        await cursor.execute("UPDATE players SET in_clan = 0 WHERE role_id = ?", (target_id,))
                        
                elif etype in [1, 2, 6] or "принят" in desc.lower() or "joined" in desc.lower():
                    await cursor.execute("UPDATE players SET in_clan = 1 WHERE role_id = ?", (rid,))
                
                # Event
                await cursor.execute("""
                    INSERT INTO events (role_id, timestamp, event_date, event_type, value, raw_desc)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (rid, row['timestamp'], row['date'], etype, val, desc))
                
                if cursor.rowcount > 0:
                    new_events += 1
                    
            await conn.commit()

        # 3. Check items to scrape
        missing_ids = set()
        if item_ids:
            async with aiosqlite.connect(web_database.DB_NAME) as conn:
                placeholders = ','.join(['?'] * len(item_ids))
                async with conn.execute(f"SELECT id FROM items WHERE id IN ({placeholders})", list(item_ids)) as cursor:
                    existing_rows = await cursor.fetchall()
                    existing_ids = {r[0] for r in existing_rows}
                
                missing_ids = item_ids - existing_ids
                logging.info(f"Missing item IDs to scrape: {missing_ids}")

        # Return success with context for background tasks
        # We always return True for pwobs scraper check if success, allowing controller to decide based on config/flag
        return {"status": "ok", "new_events": new_events, "total_parsed": len(data)}, missing_ids, True

    except Exception as e:
        logging.error(f"Error in process_log_upload: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}, set(), False
