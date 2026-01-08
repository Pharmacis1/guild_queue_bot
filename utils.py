import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# --- CONFIGURATION ---
CREDENTIALS_FILE = 'credentials.json'
SPREADSHEET_URL = 'https://docs.google.com/spreadsheets/d/16R6lsvXN-Y3_PQnx5kat5tL4KKwt5WUfhNlHK9P_PiU/edit?usp=sharing'

# НАСТРОЙКА: Какой по счету столбец читать?
# 0 = Столбец A (Первый)
# 1 = Столбец B (Второй)
TARGET_COL_INDEX = 0 

# Сколько первых строк пропускать (если там заголовки или даты)
SKIP_ROWS = 1

# --- CACHE STORAGE ---
cached_nicks = []
last_update_time = None
CACHE_DURATION = timedelta(minutes=10)

async def update_cache():
    global cached_nicks, last_update_time
    
    print("🔄 Updating Google Sheets cache...")
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)

        sheet = client.open_by_url(SPREADSHEET_URL).sheet1
        
        # Получаем всю таблицу как матрицу (список списков)
        all_rows = sheet.get_all_values()
        
        if not all_rows:
            print("❌ Таблица пуста.")
            return

        new_nicks = []
        
        # Проходимся по строкам, начиная с SKIP_ROWS (чтобы пропустить шапку)
        for i, row in enumerate(all_rows):
            if i < SKIP_ROWS:
                continue
                
            # Проверяем, существует ли в этой строке нужный столбец
            if len(row) > TARGET_COL_INDEX:
                val = str(row[TARGET_COL_INDEX]).strip()
                
                # Фильтруем мусор: добавляем, только если ник длиннее 1 символа
                # и это не заголовок (можно добавить свои проверки)
                if val and len(val) > 1:
                    new_nicks.append(val)
        
        cached_nicks = new_nicks
        last_update_time = datetime.now()
        print(f"✅ Cache updated. Loaded {len(cached_nicks)} nicknames.")
        
    except Exception as e:
        print(f"❌ Error updating Google Sheets: {e}")

async def check_google_sheet(nickname: str) -> bool:
    global cached_nicks, last_update_time

    if not last_update_time or (datetime.now() - last_update_time) > CACHE_DURATION:
        await update_cache()

    nickname_lower = nickname.strip().lower()
    allowed_list_lower = [n.lower() for n in cached_nicks]

    if nickname_lower in allowed_list_lower:
        return True
    
    return False