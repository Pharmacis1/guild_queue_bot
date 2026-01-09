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
TARGET_COL_INDEX = 1 

# Сколько первых строк пропускать
SKIP_ROWS = 1

# --- CACHE STORAGE ---
cached_nicks = []
last_update_time = None
CACHE_DURATION = timedelta(minutes=10)

async def update_cache():
    global cached_nicks, last_update_time
    
    if not SPREADSHEET_URL:
        print("❌ Error: SPREADSHEET_URL is missing.")
        return

    print(f"🔗 DEBUG: Читаю таблицу: {SPREADSHEET_URL}")
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)

        # Открываем первый лист
        sheet = client.open_by_url(SPREADSHEET_URL).sheet1
        title = sheet.title
        print(f"📄 DEBUG: Открыт лист с названием: '{title}'") # <--- ПРОВЕРЬ ЭТО ИМЯ!
        
        all_rows = sheet.get_all_values()
        
        if not all_rows:
            print("❌ Таблица пуста.")
            return

        # --- РЕНТГЕН: ПОКАЗЫВАЕМ СТРУКТУРУ ---
        # Берем вторую строку (обычно там уже данные)
        if len(all_rows) > 1:
            sample_row = all_rows[1] 
            print("\n🗺 --- КАРТА СТОЛБЦОВ (СТРОКА №2) ---")
            for idx, value in enumerate(sample_row):
                # chr(65+idx) превращает 0 в A, 1 в B...
                print(f"   Столбец {chr(65+idx)} (Index {idx}): '{value}'")
            print("------------------------------------\n")
        # ---------------------------------------

        new_nicks = []
        for i, row in enumerate(all_rows):
            if i < SKIP_ROWS: continue
            
            # Используем твой текущий настройки
            if len(row) > TARGET_COL_INDEX:
                val = str(row[TARGET_COL_INDEX]).strip()
                if val and len(val) > 1:
                    new_nicks.append(val)
        
        cached_nicks = new_nicks
        last_update_time = datetime.now()
        
    except Exception as e:
        print(f"❌ Error: {e}")

async def check_google_sheet(nickname: str) -> bool:
    global cached_nicks, last_update_time

    if not last_update_time or (datetime.now() - last_update_time) > CACHE_DURATION:
        await update_cache()

    nickname_lower = nickname.strip().lower()
    allowed_list_lower = [n.lower() for n in cached_nicks]

    if nickname_lower in allowed_list_lower:
        return True
    
    return False

# --- ЛОГИРОВАНИЕ В GOOGLE SHEETS ---

# Словарь: "Название очереди в боте" : "Название вкладки в Google"
SHEET_MAPPING = {
    "Камень доблести": "Камень доблести",
    "Метеориты": "Метеориты",
    "Жемчужины Фу Си": "Фу Си",
    "Опыт в диск": "Опыт в диск",
    "Проходки в УФ": "Проходки в УФ",
    "Знаки Единства": "Знак Единства",
    "Колода карт": "Колода",
    "Сущность карты": "Сущность карты",
    "Камень божества": "Камень божика",
    "Камни бессмертных": "Камни бессмертных",
    "Цилинь": "Цилинь"
}

async def log_reward_to_sheet(queue_name: str, main_nick: str, char_nick: str, manager_name: str, status: str = "Выдано"):
    print(f"\n🚀 DEBUG: Начинаю запись в таблицу для очереди: '{queue_name}'") # <--- ЛОВУШКА 1

    # 1. Определяем нужную вкладку
    target_sheet_name = SHEET_MAPPING.get(queue_name)
    print(f"📄 DEBUG: Целевая вкладка по словарю: '{target_sheet_name}'") # <--- ЛОВУШКА 2
    
    if not target_sheet_name:
        print(f"⚠️ DEBUG: Нет маппинга! Пробую использовать имя очереди как есть: '{queue_name}'")
        target_sheet_name = queue_name 

    try:
        # 2. Подключаемся
        print("🔌 DEBUG: Подключаюсь к Google API...") # <--- ЛОВУШКА 3
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        
        # 3. Открываем таблицу
        print(f"📂 DEBUG: Открываю таблицу по URL...") 
        sh = client.open_by_url(SPREADSHEET_URL)
        
        # 4. Открываем вкладку
        print(f"📑 DEBUG: Ищу вкладку '{target_sheet_name}'...")
        worksheet = sh.worksheet(target_sheet_name)
        
        # 5. Формируем строку
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        row = [now, queue_name, main_nick, char_nick, status]
        print(f"📝 DEBUG: Пытаюсь записать строку: {row}")
        
        # 6. Записываем
        worksheet.append_row(row, table_range="A8")
        print(f"✅ Записано в Google ('{target_sheet_name}'): {char_nick} - {status}")
        return True

    except gspread.WorksheetNotFound:
        print(f"❌ ERROR: Вкладка '{target_sheet_name}' НЕ НАЙДЕНА в таблице!")
        print("   Проверь название листа на пробелы и регистр.")
        return False
    except gspread.exceptions.APIError as e:
        print(f"❌ ERROR: Ошибка API Гугла. Возможно, нет прав 'Редактора'.")
        print(f"   Детали: {e}")
        return False
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        # Выводим полный текст ошибки, чтобы понять причину
        import traceback
        traceback.print_exc()
        return False