import sqlite3

def analyze():
    conn = sqlite3.connect('guild_bot_2026-03-01_01-00-00.db')
    cursor = conn.cursor()

    query = """
    SELECT 
        strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as hour, 
        COUNT(*) as count
    FROM events 
    WHERE timestamp IS NOT NULL
    GROUP BY hour 
    ORDER BY count DESC
    """
    cursor.execute(query)
    print("Events by Hour (Localtime):")
    for row in cursor.fetchall():
        print(f"Hour {row[0]}: {row[1]} events")

    query2 = """
    SELECT 
        strftime('%w', datetime(timestamp, 'unixepoch', 'localtime')) as weekday, 
        COUNT(*) as count
    FROM events 
    WHERE timestamp IS NOT NULL
    GROUP BY weekday 
    ORDER BY weekday
    """
    cursor.execute(query2)
    print("\nEvents by Weekday (0=Sunday, 3=Wednesday...):")
    for row in cursor.fetchall():
        print(f"Weekday {row[0]}: {row[1]} events")
        
    query3 = """
    SELECT 
        strftime('%w', datetime(timestamp, 'unixepoch', 'localtime')) as weekday,
        strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as hour, 
        COUNT(*) as count
    FROM events 
    WHERE timestamp IS NOT NULL
    GROUP BY weekday, hour
    ORDER BY weekday, count DESC
    """
    cursor.execute(query3)
    print("\nTop 5 hours per weekday (Localtime):")
    from itertools import groupby
    rows = cursor.fetchall()
    for weekday, group in groupby(rows, key=lambda x: x[0]):
        print(f"\nWeekday {weekday}:")
        for i, row in enumerate(group):
            if i < 5:
                print(f"  Hour {row[1]}: {row[2]} events")

if __name__ == '__main__':
    analyze()
