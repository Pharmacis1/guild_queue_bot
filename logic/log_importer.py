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

        new_events = 0
        item_ids = set()

        # 2. Write to DB
        async with AsyncSessionLocal() as session:
            # Current MSK time
            current_msk = datetime.datetime.now(pytz.timezone("Europe/Moscow"))
            current_ts = int(current_msk.timestamp())

            # Pre-fetch known nicknames for description replacement
            all_involved_ids = set()
            for row in data:
                all_involved_ids.add(row["role_id"])
                if row["raw_params"]:
                    try:
                        p0 = int(row["raw_params"].split(",")[0])
                        all_involved_ids.add(p0)
                    except Exception:
                        pass

            # Fetch existing nicknames
            id_to_nick = {}
            if all_involved_ids:
                result = await session.execute(
                    select(Player.role_id, Player.nickname).filter(Player.role_id.in_(list(all_involved_ids)))
                )
                for r_id, r_nick in result.all():
                    if r_nick:
                        id_to_nick[r_id] = r_nick

            for row in data:
                rid = row["role_id"]

                # Check if event is from the future (in MSK, with 24h leeway)
                if row["timestamp"] > current_ts + 86400:
                    logging.warning(f"Skipping future event for role_id {rid} at {row['date']}")
                    continue

                # Filter invalid IDs (like ID 1)
                if rid < 16:
                    continue

                etype = row["action_type"]
                desc = row["description"]

                val = 0
                target_id = None

                if row["raw_params"]:
                    try:
                        val = int(row["raw_params"].split(",")[0])
                        target_id = val
                        if etype == 0:  # Item event
                            item_ids.add(val)
                    except Exception:
                        pass

                # Resolve ID in description
                if target_id and f"ID {target_id}" in desc:
                    t_nick = id_to_nick.get(target_id)
                    if t_nick:
                        desc = desc.replace(f"ID {target_id}", f"{t_nick}")

                # Ensure actor exists
                existing = await session.execute(select(Player).filter_by(role_id=rid))
                if not existing.scalar_one_or_none():
                    session.add(Player(role_id=rid, in_clan=1))
                    await session.flush()

                # Status Updates
                is_leave_self = etype == 8  # Покинул гильдию
                is_kick = etype == 10  # Изгнал ID ...

                if is_leave_self:
                    await session.execute(update(Player).filter_by(role_id=rid).values(in_clan=0))

                elif is_kick:
                    if target_id:
                        existing_target = await session.execute(select(Player).filter_by(role_id=target_id))
                        if not existing_target.scalar_one_or_none():
                            session.add(Player(role_id=target_id, in_clan=1))
                            await session.flush()
                        await session.execute(update(Player).filter_by(role_id=target_id).values(in_clan=0))

                elif etype in [1, 2, 6] or "принят" in desc.lower() or "joined" in desc.lower():
                    await session.execute(update(Player).filter_by(role_id=rid).values(in_clan=1))

                # Insert Event
                # [DEDUPLICATION] Check if this event already exists to avoid duplicates
                stmt_check = select(Event).filter_by(
                    role_id=rid,
                    timestamp=row["timestamp"],
                    event_type=etype,
                    value=val
                )
                res_check = await session.execute(stmt_check)
                if res_check.scalar_one_or_none():
                    logging.info(f"Skipping duplicate event for role_id {rid} at {row['date']}")
                    continue

                new_event = Event(
                    role_id=rid,
                    timestamp=row["timestamp"],
                    event_date=row["date"],
                    event_type=etype,
                    value=val,
                    raw_desc=desc,
                )
                session.add(new_event)
                new_events += 1

            await session.commit()

        # 3. Check items to scrape
        missing_ids = set()
        if item_ids:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Item.id).filter(Item.id.in_(list(item_ids)))
                )
                existing_ids = {r[0] for r in result.all()}
                missing_ids = item_ids - existing_ids
                logging.info(f"Missing item IDs to scrape: {missing_ids}")

        return {"status": "ok", "new_events": new_events, "total_parsed": len(data)}, missing_ids, True

    except Exception as e:
        logging.error(f"Error in process_log_upload: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}, set(), False
