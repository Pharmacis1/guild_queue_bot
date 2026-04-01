from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple

def analyze_events_stats(events: List[Tuple[float, int, int]]) -> Dict[str, Any]:
    """
    Analyzes player event list.
    events: List of (timestamp, value, event_type)
    Returns a dictionary with all counters and details for tooltips.
    """
    stats = {
        "s1": 0, "s2": 0, "s3": 0, "s4": 0, "s5": 0, "s6": 0, "s7": 0,
        "adepts": 0, "dances": 0, "total_gold": 0, "total_valor": 0,
        "s1_details": [], "s2_details": [], "s3_details": [], "s4_details": [],
        "s5_details": [], "s6_details": [], "s7_details": [], "valor_details": [],
        "adepts_details": [], "dances_details": []
    }

    # Sort by timestamp
    events.sort(key=lambda x: x[0] if x[0] else 0)

    # Russian short days
    DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    def fmt_date_rich(ts):
        if not ts: return ""
        dt = datetime.fromtimestamp(ts, timezone(timedelta(hours=3)))
        d_str = dt.strftime("%d.%m")
        t_str = dt.strftime("%H:%M")
        wd = DAYS_RU[dt.weekday()]
        return f"{d_str} {t_str} ({wd})"

    for i, (ts, val, etype) in enumerate(events):
        d_str_rich = fmt_date_rich(ts)

        # Gold
        if etype == 2:
            stats["total_gold"] += (val or 0)
            continue

        # Valor
        if etype == 1:
            stats["total_valor"] += (val or 0)
            
            detail_label = ""
            # Stages
            if val == 4:
                is_dance = False
                # Check backward (< 20 min)
                if i > 0:
                    prev_ts, prev_val, prev_type = events[i - 1]
                    if prev_type == 1 and prev_val == 2 and ts and prev_ts and (ts - prev_ts) < 1200:
                        is_dance = True

                # Check forward (< 20 min)
                if not is_dance and i < len(events) - 1:
                    next_ts, next_val, next_type = events[i + 1]
                    if next_type == 1 and next_val == 8 and next_ts and ts and (next_ts - ts) < 1200:
                        is_dance = True

                if is_dance:
                    stats["dances"] += 1
                    stats["dances_details"].append(f"{d_str_rich} +{val}")
                    detail_label = f"Танцы (4)"
                else:
                    stats["s1"] += 1
                    stats["s1_details"].append(f"{d_str_rich} +{val}")
                    detail_label = f"Этап I (4)"

            elif val == 6:
                stats["s2"] += 1
                stats["s2_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Этап II (6)"
            elif val == 10:
                stats["s3"] += 1
                stats["s3_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Этап III (10)"
            elif val == 14:
                stats["s4"] += 1
                stats["s4_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Этап IV (14)"
            elif val == 24:
                stats["s5"] += 1
                stats["s5_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Этап V (24)"
            elif val == 40:
                stats["s6"] += 1
                stats["s6_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Этап VI (40)"
            elif val == 70:
                stats["s7"] += 1
                stats["s7_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Этап VII (70)"
            elif val == 7:
                stats["adepts"] += 1
                stats["adepts_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Адепты (7)"
            elif val in [2, 8]:
                stats["dances"] += 1
                stats["dances_details"].append(f"{d_str_rich} +{val}")
                detail_label = f"Танцы ({val})"
            else:
                detail_label = f"Доблесть ({val})"
            
            if detail_label:
                stats["valor_details"].append(f"{d_str_rich}: {detail_label}")

    return stats
