from datetime import datetime, timedelta


def is_newcomer(role_id: int, join_dates_map: dict, ref_date_str: str = None) -> bool:
    """
    Determines if a player is a newcomer (joined within 14 days from now).

    Args:
        role_id: The player's role ID.
        join_dates_map: Dictionary mapping role_id to join_date string (YYYY-MM-DD ...).
        ref_date_str: Ignored, kept for backward compatibility.
    """
    if not role_id or role_id not in join_dates_map:
        return False
    try:
        val = join_dates_map[role_id]
        if " " in val:
            val = val.split()[0]
        join_dt = datetime.strptime(val, "%Y-%m-%d")

        now = datetime.now()
        # "Real time" check: < 2 weeks (14 days)
        return (now - join_dt).days < 14
    except Exception:
        return False
