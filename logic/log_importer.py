import datetime
import pytz
import logging
from typing import Any, Dict, Set, Tuple

from sqlalchemy import select, update, func

from database import AsyncSessionLocal, Player, Event, Item

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

        # 2. Extract involved IDs and time range
        involved_ids = set()
        min_ts = float("inf")
        max_ts = float("-inf")
        
        for row in data:
            involved_ids.add(row["role_id"])
            min_ts = min(min_ts, row["timestamp"])
            max_ts = max(max_ts, row["timestamp"])
            if row["raw_params"]:
                try:
                    p0 = int(row["raw_params"].split(",")[0])
                    involved_ids.add(p0)
                except Exception:
                    pass
        
        involved_ids = [rid for rid in involved_ids if rid >= 16] # Filter invalid IDs early

        # 3. Batch fetch existing data from DB
        async with AsyncSessionLocal() as session:
            # Current MSK time for future check
            current_msk = datetime.datetime.now(pytz.timezone("Europe/Moscow"))
            current_ts_now = int(current_msk.timestamp())

            # Fetch players
            players_result = await session.execute(
                select(Player).filter(Player.role_id.in_(involved_ids))
            )
            players_map = {p.role_id: p for p in players_result.scalars().all()}
            id_to_nick = {rid: p.nickname for rid, p in players_map.items() if p.nickname}

            # Fetch existing events for deduplication
            # Use a slightly wider window to be safe (+- 1 second?) No, exact is usually fine.
            events_result = await session.execute(
                select(Event.role_id, Event.timestamp, Event.event_type, Event.value)
                .filter(Event.role_id.in_(involved_ids))
                .filter(Event.timestamp >= min_ts)
                .filter(Event.timestamp <= max_ts)
            )
            existing_events_set = set()
            for r_id, ts, etype, val in events_result.all():
                # For Join/Leave, value was ignored in the previous code's check_params
                if etype in [6, 8]:
                    existing_events_set.add((r_id, ts, etype))
                else:
                    existing_events_set.add((r_id, ts, etype, val))

            # 4. Process records in memory
            new_events_to_add = []
            item_ids = set()
            clan_status_updates = {} # rid -> status
            new_players_ids = set()
            
            # Process in reverse order (Oldest -> Newest)
            for row in reversed(data):
                rid = row["role_id"]
                if rid < 16: continue
                
                # Future check
                if row["timestamp"] > current_ts_now + 86400:
                    continue

                etype = row["action_type"]
                desc = row["description"]
                val = 0
                target_id = None

                if row["raw_params"]:
                    try:
                        val = int(row["raw_params"].split(",")[0])
                        target_id = val
                        if etype == 0:
                            item_ids.add(val)
                    except Exception:
                        pass

                # Resolve ID in description
                if target_id and f"ID {target_id}" in desc:
                    t_nick = id_to_nick.get(target_id)
                    if t_nick:
                        desc = desc.replace(f"ID {target_id}", f"{t_nick}")

                # Actor existence
                if rid not in players_map and rid not in new_players_ids:
                    new_players_ids.add(rid)

                # Clan Status Logic
                is_leave_self = etype == 8
                is_kick = etype == 10

                if is_leave_self:
                    clan_status_updates[rid] = 0
                elif is_kick:
                    if target_id and target_id >= 16:
                        if target_id not in players_map and target_id not in new_players_ids:
                            new_players_ids.add(target_id)
                        clan_status_updates[target_id] = 0
                elif etype in [1, 2, 6] or "принят" in desc.lower() or "joined" in desc.lower():
                    clan_status_updates[rid] = 1

                # Deduplication Check
                if etype in [6, 8]:
                    check_key = (rid, row["timestamp"], etype)
                else:
                    check_key = (rid, row["timestamp"], etype, val)
                
                if check_key in existing_events_set:
                    continue
                
                # Store for bulk insert
                new_event = Event(
                    role_id=rid,
                    timestamp=row["timestamp"],
                    event_date=row["date"],
                    event_type=etype,
                    value=val,
                    raw_desc=desc,
                )
                new_events_to_add.append(new_event)
                # Avoid adding the same event twice if it appears twice in the same log (unlikely but possible)
                existing_events_set.add(check_key)

            # 5. Flush to DB
            # Add new players
            for npid in new_players_ids:
                status = clan_status_updates.get(npid, 1) # Default to 1 if joining or just appearing
                p = Player(role_id=npid, in_clan=status)
                session.add(p)
                # No longer pending update
                if npid in clan_status_updates:
                    del clan_status_updates[npid]

            # Update existing players' statuses
            for rid, status in clan_status_updates.items():
                if rid in players_map:
                    players_map[rid].in_clan = status

            # Bulk insert events
            if new_events_to_add:
                session.add_all(new_events_to_add)

            await session.commit()

        # 6. Check items to scrape (same as before)
        missing_ids = set()
        if item_ids:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Item.id).filter(Item.id.in_(list(item_ids)))
                )
                existing_ids = {r[0] for r in result.all()}
                missing_ids = item_ids - existing_ids

        return {"status": "ok", "new_events": len(new_events_to_add), "total_parsed": len(data)}, missing_ids, True

    except Exception as e:
        logging.error(f"Error in process_log_upload: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}, set(), False

