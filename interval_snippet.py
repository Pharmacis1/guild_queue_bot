from datetime import datetime, timedelta


def get_intervals(start_date_str, end_date_str, period, count=1):
    """
    Generates a list of intervals [(label, start_dt, end_dt)]
    Period: 'day', 'week', 'month', 'year'
    """
    s_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    e_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    
    intervals = []
    
    current = s_date
    while current <= e_date:
        interval_start = current
        
        if period == 'day':
            interval_end = current + timedelta(days=count - 1)
            next_start = interval_end + timedelta(days=1)
            label = interval_start.strftime("%d.%m")
            
        elif period == 'week':
            # Align to Monday? No, just chunks of 7 days logic or calendar weeks?
            # User said: "periods take with binding to real weeks, months, years"
            
            # If we want REAL calendar weeks:
            # First interval starts at 'current' (which might be mid-week if global range set so)
            # OR we assume global range is already aligned? 
            # Let's align 'current' to Monday if it's the very first iteration? 
            # Actually, standard is usually: The GLOBAL range defines the bounds. 
            # We just slice that global range.
            # BUT user said "binding to real weeks".
            
            # Logic:
            # 1. Start from s_date.
            # 2. Find the end of that "real week" (Sunday).
            # 3. Interval is [current, Sunday].
            # 4. Next starts Monday.
            
            # Simple approach: 
            # Iterate by calendar weeks.
            # For the first interval, it might be partial if s_date is Wed.
            
            # Find Sunday of current week
            days_to_sunday = 6 - current.weekday()
            interval_end = current + timedelta(days=days_to_sunday)
            
            # If period count > 1 (e.g. 2 weeks grouped), we add (count-1) * 7 days
            if count > 1:
                interval_end += timedelta(weeks=count-1)
                
            next_start = interval_end + timedelta(days=1)
            
            # Cap at e_date
            if interval_end > e_date:
                interval_end = e_date
                
            # Label
            label = f"{interval_start.strftime('%d.%m')} - {interval_end.strftime('%d.%m')}"
            
        elif period == 'month':
            # Real months
            # Find last day of current month
            # Logic: 1st of next month - 1 day
            next_month_first = (current.replace(day=1) + timedelta(days=32)).replace(day=1)
            interval_end = next_month_first - timedelta(days=1)
            
            if count > 1:
                 # Add more months... complicated logic, simplify to 1 month for now or simple loop
                 for _ in range(count - 1):
                     next_month_first = (next_month_first + timedelta(days=32)).replace(day=1)
                     interval_end = next_month_first - timedelta(days=1)
            
            next_start = interval_end + timedelta(days=1)
            
            if interval_end > e_date:
                interval_end = e_date
            
            label = interval_start.strftime("%b %Y") # e.g. Jan 2024
            
        elif period == 'year':
            interval_end = current.replace(month=12, day=31)
             # Handle count > 1 ...
            next_start = interval_end + timedelta(days=1)
             
            if interval_end > e_date:
                interval_end = e_date
            
            label = interval_start.strftime("%Y")

        else:
             # Fallback
             break
             
        intervals.append({
            'label': label,
            'start': interval_start,
            'end': interval_end
        })
        
        current = next_start
        
    return intervals
