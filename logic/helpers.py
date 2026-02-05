from datetime import datetime, timedelta


def is_newcomer(role_id: int, join_dates_map: dict, ref_date_str: str) -> bool:
    """
    Determines if a player is a newcomer (joined within the current week scope).
    
    Args:
        role_id: The player's role ID.
        join_dates_map: Dictionary mapping role_id to join_date string (YYYY-MM-DD ...).
        ref_date_str: The reference date string (YYYY-MM-DD or None) used as 'current' context 
                      (often start of week or similar). logic uses < 7 days from ref_monday.
    """
    if not role_id or role_id not in join_dates_map: return False
    try:
        val = join_dates_map[role_id]
        if ' ' in val: val = val.split()[0]
        join_dt = datetime.strptime(val, "%Y-%m-%d")
        
        # If ref_date_str is passed, parse it. Otherwise use today?
        # Logic from views looks like it uses `current_kh_start` (or similar) as ref.
        
        if not ref_date_str: return False
        
        ref_dt = datetime.strptime(ref_date_str, "%Y-%m-%d")
        ref_monday = ref_dt - timedelta(days=ref_dt.weekday())
        
        return (ref_monday - join_dt).days < 7
    except:
        return False
