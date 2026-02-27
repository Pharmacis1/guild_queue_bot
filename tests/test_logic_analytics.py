import pytest
from logic import analytics

# --- calculate_thresholds ---

def test_calculate_thresholds_large_list():
    # 100 values from 1 to 100
    values = list(range(1, 101))
    
    thresholds = analytics.calculate_thresholds(values)
    
    # Total = 100.
    # Top 5% (Gold): ceil(100*0.95)-1 = 94. Index 94 value = 95.
    assert thresholds["gold"] == 95
    
    # Top 15% (Silver): ceil(100*0.85)-1 = 84. Index 84 value = 85.
    assert thresholds["silver"] == 85
    
    # Top 10 absolute: index -10 value = 91.
    assert thresholds["top10"] == 91

def test_calculate_thresholds_small_list():
    # Less than 10 values
    values = [10, 20, 30, 40, 50]
    
    thresholds = analytics.calculate_thresholds(values)
    
    # Total = 5.
    # Gold: ceil(5 * 0.95) - 1 = ceil(4.75) - 1 = 5 - 1 = 4. Index 4 = 50.
    assert thresholds["gold"] == 50
    # Silver: ceil(5 * 0.85) - 1 = ceil(4.25) - 1 = 5 - 1 = 4. Index 4 = 50.
    assert thresholds["silver"] == 50
    
    # Top 10 Absolute (falls back to lowest value since < 10)
    assert thresholds["top10"] == 10

def test_calculate_thresholds_empty_and_zeros():
    # All zeros are filtered out
    values = [0, 0, 0]
    thresholds = analytics.calculate_thresholds(values)
    assert thresholds["gold"] == 999999999
    assert thresholds["silver"] == 999999999
    assert thresholds["top10"] == 999999999
    
    thresholds_empty = analytics.calculate_thresholds([])
    assert thresholds_empty["gold"] == 999999999

# --- calculate_gold_thresholds ---

def test_calculate_gold_thresholds_large_list():
    values = list(range(1, 21)) # 20 items
    thresholds = analytics.calculate_gold_thresholds(values)
    
    # Greater than 10, should take index -10 = 11
    assert thresholds["top10"] == 11

def test_calculate_gold_thresholds_small_list():
    values = [10, 20, 30, 40, 50] # 5 items
    thresholds = analytics.calculate_gold_thresholds(values)
    
    # Less than 10. Total=5, max(1, 5//2) = max(1, 2) = 2.
    # Index = -2. Value = 40.
    assert thresholds["top10"] == 40
    
    values_tiny = [10]
    thresholds_tiny = analytics.calculate_gold_thresholds(values_tiny)
    # Total=1. 1//2 = 0. max(1, 0) = 1. Index -1 = 10.
    assert thresholds_tiny["top10"] == 10

def test_calculate_gold_thresholds_empty():
    thresholds = analytics.calculate_gold_thresholds([0, 0])
    assert thresholds["top10"] == 999999999

# --- get_valor_tier ---

def test_get_valor_tier_zero():
    assert analytics.get_valor_tier(0, [100, 200], {"top10": 100}, 10) == 0

def test_get_valor_tier_top10():
    # Value is exactly the threshold
    assert analytics.get_valor_tier(150, [50, 100, 150, 200], {"top10": 150}, days_diff=4) == 6
    assert analytics.get_valor_tier(150, [50, 100, 150, 200], {"top10": 150}, days_diff=3) == 7

def test_get_valor_tier_empty_list():
    # value not 0, but total active equals 0
    assert analytics.get_valor_tier(10, [], {"top10": 999999999}, 5) == 1

def test_get_valor_tier_percentiles():
    active_vals = list(range(10, 110, 10)) # 10 items (10 .. 100)
    # Threshold intentionally high so we fall back to percentiles
    thresholds = {"top10": 999}
    
    # pct = rank / 10
    # rank of 95: bisect_right -> 9. pct = 0.9. (>0.8)
    assert analytics.get_valor_tier(95, active_vals, thresholds, days_diff=4) == 5
    assert analytics.get_valor_tier(95, active_vals, thresholds, days_diff=3) == 7
    
    # rank of 75 -> 7. pct = 0.7. (>0.6)
    assert analytics.get_valor_tier(75, active_vals, thresholds, days_diff=10) == 4
    
    # rank of 55 -> 5. pct = 0.5 (>0.4)
    assert analytics.get_valor_tier(55, active_vals, thresholds, days_diff=10) == 3
    
    # rank of 35 -> 3. pct = 0.3 (>0.2)
    assert analytics.get_valor_tier(35, active_vals, thresholds, days_diff=10) == 2
    
    # rank of 15 -> 1. pct = 0.1 (else)
    assert analytics.get_valor_tier(15, active_vals, thresholds, days_diff=10) == 1

# --- get_gold_tier ---

def test_get_gold_tier_zero():
    assert analytics.get_gold_tier(0, [100, 200], {"top10": 100}, 10) == 0

def test_get_gold_tier_top10():
    assert analytics.get_gold_tier(150, [50, 100, 150, 200], {"top10": 150}, days_diff=4) == 6
    assert analytics.get_gold_tier(150, [50, 100, 150, 200], {"top10": 150}, days_diff=3) == 7

def test_get_gold_tier_empty_list():
    assert analytics.get_gold_tier(10, [], {"top10": 999999999}, 5) == 1

def test_get_gold_tier_percentiles():
    active_vals = list(range(10, 110, 10))
    thresholds = {"top10": 999}
    
    assert analytics.get_gold_tier(95, active_vals, thresholds, days_diff=4) == 5
    assert analytics.get_gold_tier(95, active_vals, thresholds, days_diff=3) == 7
    assert analytics.get_gold_tier(75, active_vals, thresholds, days_diff=10) == 4
    assert analytics.get_gold_tier(55, active_vals, thresholds, days_diff=10) == 3
    assert analytics.get_gold_tier(35, active_vals, thresholds, days_diff=10) == 2
    assert analytics.get_gold_tier(15, active_vals, thresholds, days_diff=10) == 1
