from web_database import get_intervals


# Test cases
def test_intervals():
    print("Testing Daily...")
    daily = get_intervals("2024-01-01", "2024-01-05", "day", 1)
    print(f"Daily: {len(daily)} intervals")
    for i in daily:
        print(f"  {i['label']}: {i['start']} -> {i['end']}")
        
    print("\nTesting Weekly (1 month range)...")
    weekly = get_intervals("2024-01-01", "2024-01-31", "week", 1)
    print(f"Weekly: {len(weekly)} intervals")
    for i in weekly:
        print(f"  {i['label']}: {i['start']} -> {i['end']}")

    # Edge case: Period count > 1
    print("\nTesting Weekly (Count=2)...")
    weekly2 = get_intervals("2024-01-01", "2024-01-31", "week", 2)
    print(f"Weekly2: {len(weekly2)} intervals")
    for i in weekly2:
        print(f"  {i['label']}: {i['start']} -> {i['end']}")

test_intervals()
