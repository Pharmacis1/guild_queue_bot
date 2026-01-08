import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from dotenv import load_dotenv # Нужно для чтения .env

# Загружаем переменные из .env
load_dotenv()

# --- CONFIGURATION ---
CREDENTIALS_FILE = 'credentials.json'

# ТЕПЕРЬ БЕРЕМ ИЗ ПЕРЕМЕННОЙ ОКРУЖЕНИЯ
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL") 

# Проверка на случай, если забыли добавить в .env
if not SPREADSHEET_URL:
    print("⚠️ WARNING: SPREADSHEET_URL not found in .env file!")

# НАСТРОЙКА: Какой по счету столбец читать?
# 0 = Столбец A (Первый)
TARGET_COL_INDEX = 0 

# Сколько первых строк пропускать
SKIP_ROWS = 1

# --- CACHE STORAGE ---
cached_nicks = []
last_update_time = None
CACHE_DURATION = timedelta(minutes=10)

async def update_cache():
    global cached_nicks, last_update_time
    
    # Если ссылки нет - выходим сразу, чтобы не сломать бота
    if not SPREADSHEET_URL:
        print("❌ Error: SPREADSHEET_URL is missing.")
        return

    print("🔄 Updating Google Sheets cache...")
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)

        sheet = client.open_by_url(SPREADSHEET_URL).sheet1
        
        all_rows = sheet.get_all_values()
        
        if not all_rows:
            print("❌ Таблица пуста.")
            return

        new_nicks = []
        
        for i, row in enumerate(all_rows):
            if i < SKIP_ROWS:
                continue
            
            if len(row) > TARGET_COL_INDEX:
                val = str(row[TARGET_COL_INDEX]).strip()
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