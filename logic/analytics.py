import bisect
import math
from typing import Dict, List


def calculate_thresholds(values: List[int]) -> Dict[str, int]:
    """
    Calculates tier thresholds based on a sorted list of active values (ascending).
    Returns a dict with 'gold', 'silver', 'top10' thresholds.
    """
    sorted_vals = sorted([v for v in values if v > 0])
    total = len(sorted_vals)
    
    thresholds = {
        'gold': 999999999,
        'silver': 999999999,
        'top10': 999999999
    }
    
    if total > 0:
        # Top 5% for Gold (Index: ceil(total*0.95)-1)
        # e.g. 100 items. 95th item (index 94) -> top 5% are index 95-99 (5 items).
        # Wait, if I have indices 0..99.
        # Top 5% means the best 5. Indices 95, 96, 97, 98, 99.
        # Threshold should be the value at index 95?
        # Current logic: `max(0, math.ceil(total*0.95)-1)`
        # 100 * 0.95 = 95. ceil(95)-1 = 94.
        # Value at 94.
        # If I have 100 values. sorted_vals[94] is the start of top 6%?
        # Let's trust the logic I'm extracting for now, or improve it if it looks buggy.
        # "Gold" usually means "Better than threshold".
        
        idx_gold = max(0, math.ceil(total * 0.95) - 1)
        thresholds['gold'] = sorted_vals[idx_gold]
        
        idx_silver = max(0, math.ceil(total * 0.85) - 1)
        thresholds['silver'] = sorted_vals[idx_silver]
        
        # Top 10 Absolute
        if total >= 10:
            thresholds['top10'] = sorted_vals[-10]
        else:
            thresholds['top10'] = sorted_vals[0] # All are top 10 if < 10
            
    return thresholds

def calculate_gold_thresholds(values: List[int]) -> Dict[str, int]:
    """
    Specific logic for Gold (Currency) stats if different?
    Original code:
    t_g_10 = ...
    if total >= 10: -10 else -max(1, total//2)
    This is different from Valor logic.
    """
    sorted_vals = sorted([v for v in values if v > 0])
    total = len(sorted_vals)
    
    thresholds = {'top10': 999999999}
    
    if total > 0:
        if total >= 10:
            thresholds['top10'] = sorted_vals[-10]
        else:
            # Top half?
            idx = -max(1, total // 2)
            thresholds['top10'] = sorted_vals[idx]
            
    return thresholds

def get_valor_tier(value: int, sorted_active_values: List[int], thresholds: Dict[str, int], days_diff: int) -> int:
    """
    Determines the visual tier (1-7) for Valor.
    """
    if value == 0: return 0
    
    # 1. Top 10 / Threshold Check
    # Logic from views: 
    # if val >= t_v_10: row['valor_tier'] = 6 if days_diff >=4 else 7
    # Wait, 7 is usually "Shine/Sparkle"?
    # If days >= 4 (long period), tier 6 (Gold Border).
    # If short period (days < 4), tier 7 (Rainbow/Sparkle)?
    # Need to check semantic of 6 vs 7.
    # Actually usually 7 is "Grandmaster" or similar.
    
    # Original:
    # if val >= t_v_10: row['valor_tier'] = 6 if days_diff >=4 else 7
    
    if value >= thresholds['top10']:
        return 6 if days_diff >= 4 else 7
        
    # 2. Percentile Rank (Bisect)
    # rank = bisect.bisect_right(kh_active_valors, val)
    # pct = rank / total_active
    
    total = len(sorted_active_values)
    if total == 0: return 1
    
    rank = bisect.bisect_right(sorted_active_values, value)
    pct = rank / total
    
    if pct > 0.8:
        return 5 if days_diff >= 4 else 7
    elif pct > 0.6:
        return 4
    elif pct > 0.4:
        return 3
    elif pct > 0.2:
        return 2
    else:
        return 1
    
def get_gold_tier(value: int, sorted_active_values: List[int], thresholds: Dict[str, int], days_diff: int) -> int:
    """
    Determines the visual tier (1-7) for Gold.
    """
    if value == 0: return 0
    
    if value >= thresholds['top10']:
        return 6 if days_diff >= 4 else 7
        
    total = len(sorted_active_values)
    if total == 0: return 1
    
    rank = bisect.bisect_right(sorted_active_values, value)
    pct = rank / total
    
    if pct > 0.8:
        return 5 if days_diff >= 4 else 7
    elif pct > 0.6:
        return 4
    elif pct > 0.4:
        return 3
    elif pct > 0.2:
        return 2
    else:
        return 1
