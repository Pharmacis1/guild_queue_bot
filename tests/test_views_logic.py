import asyncio
from datetime import datetime, timedelta

import aiosqlite

from web_database import DB_NAME, get_data_from_db


async def test_logic():
    print("Testing Views Logic...")

    # Defaults
    today = datetime.now()
    days_to_monday = today.weekday()
    monday = today - timedelta(days=days_to_monday)
    current_kh_start = monday.strftime("%Y-%m-%d")
    current_kh_end = today.strftime("%Y-%m-%d")

    print(f"Date Range: {current_kh_start} - {current_kh_end}")

    # Fetch
    kh_rows_raw, kh_s, kh_e, _ = await get_data_from_db(current_kh_start, current_kh_end, None, None, 1)
    print(f"Raw Rows: {len(kh_rows_raw)}")

    kh_rows_filtered = kh_rows_raw  # No class filter

    # Join Dates Logic (Mocked or Real)
    try:
        async with aiosqlite.connect(DB_NAME) as conn:
            cursor = await conn.execute("SELECT role_id, first_seen FROM players WHERE in_clan = 1")
            join_data = await cursor.fetchall()
            join_dates = {role_id: first_seen for role_id, first_seen in join_data if first_seen}
    except Exception as e:
        print(f"DB Error: {e}")
        join_dates = {}

    def is_newcomer_func(role_id, ref_date_str):
        if not role_id or role_id not in join_dates:
            return False
        try:
            val = join_dates[role_id]
            if " " in val:
                val = val.split()[0]
            join_dt = datetime.strptime(val, "%Y-%m-%d")
            ref_dt = datetime.strptime(ref_date_str, "%Y-%m-%d")
            ref_monday = ref_dt - timedelta(days=ref_dt.weekday())
            return (ref_monday - join_dt).days < 7
        except Exception:
            return False

    # Processing
    final_kh_rows = []

    kh_active_valors = sorted([r["total_valor"] for r in kh_rows_raw if r["total_valor"] > 0])
    total_active = len(kh_active_valors)
    print(f"Total Active Valor Users: {total_active}")

    for r in kh_rows_filtered:
        row = dict(r)
        row["is_newcomer"] = is_newcomer_func(row.get("role_id"), kh_s)
        final_kh_rows.append(row)

    print(f"Final Rows: {len(final_kh_rows)}")
    if len(final_kh_rows) > 0:
        print("First Row:", final_kh_rows[0])


if __name__ == "__main__":
    asyncio.run(test_logic())
