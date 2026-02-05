import os
import sqlite3

DB_PATH = "guild_bot.db"

QUEUES_TO_REMOVE = [
    "Камень доблести", 
    "Метеориты", 
    "Опыт в диск", 
    "Проходки в УФ", 
    "Камни бессмертных"
]

def disable_queues():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("--- Disabling Queues ---")
    
    # 1. Disable Queue Types
    placeholders = ','.join(['?'] * len(QUEUES_TO_REMOVE))
    sql_find = f"SELECT id, name FROM queue_types WHERE name IN ({placeholders})"
    
    cursor.execute(sql_find, QUEUES_TO_REMOVE)
    found_queues = cursor.fetchall()
    
    if not found_queues:
        print("No target queues found in DB.")
        conn.close()
        return

    ids_to_disable = [row[0] for row in found_queues]
    names_disabled = [row[1] for row in found_queues]
    
    print(f"Found queues to disable: {names_disabled} (IDs: {ids_to_disable})")
    
    # Update is_active = 0
    sql_update = f"UPDATE queue_types SET is_active = 0 WHERE id IN ({','.join(map(str, ids_to_disable))})"
    cursor.execute(sql_update)
    print(f"Marked {cursor.rowcount} queues as inactive.")

    # 2. Delete Active Entries for these queues
    sql_delete_entries = f"DELETE FROM queue_entries WHERE queue_type_id IN ({','.join(map(str, ids_to_disable))})"
    cursor.execute(sql_delete_entries)
    print(f"Deleted {cursor.rowcount} active queue entries for these queues.")

    conn.commit()
    conn.close()
    print("--- Done ---")

if __name__ == "__main__":
    disable_queues()
