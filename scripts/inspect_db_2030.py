import sqlite3
import os

db_path = r"c:\dev\guild_queue_bot\guild_bot_2026-02-13_13-20-30_manual_user.db"
output_file = r"c:\dev\guild_queue_bot\found_rows.txt"

if not os.path.exists(db_path):
    print(f"Database file not found: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

with open(output_file, "w", encoding="utf-8") as f:
    f.write(f"Scanning {len(tables)} tables for '2030'...\n")
    
    found_rows = False

    for table_name in tables:
        table = table_name[0]
        try:
            # Get all columns for the table
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [info[1] for info in cursor.fetchall()]
            
            # Construct a query to search for '2030' in all columns
            query_parts = []
            for col in columns:
                query_parts.append(f"\"{col}\" LIKE '%2030%'")
            
            if not query_parts:
                continue
                
            where_clause = " OR ".join(query_parts)
            query = f"SELECT * FROM \"{table}\" WHERE {where_clause}"
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            if rows:
                f.write(f"TABLE: {table}\n")
                found_rows = True
                for row in rows:
                    f.write(f"  ROW: {row}\n")
        except Exception as e:
            f.write(f"  Error checking table {table}: {e}\n")

    if not found_rows:
        f.write("No rows containing '2030' were found.\n")

conn.close()
print(f"Done. Results written to {output_file}")
