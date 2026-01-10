from aiogram import types

# --- INLINE KEYBOARDS ---

def get_main_menu(user):
    kb = [
        [types.InlineKeyboardButton(text="👥 Мои персонажи", callback_data="menu_chars")],
        [types.InlineKeyboardButton(text="✍️ Записаться в очередь", callback_data="menu_join")],
        [types.InlineKeyboardButton(text="📜 Моя история получения наград", callback_data="menu_history")],
        [types.InlineKeyboardButton(text="ℹ️ Инфо об очередях", callback_data="menu_info")],
        [types.InlineKeyboardButton(text="🏃 Управление записями в очереди", callback_data="my_active_queues")]
    ]
    if user.is_master:
        kb.append([types.InlineKeyboardButton(text="👑 Панель Мастера", callback_data="menu_master")])
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def get_master_menu():
    kb = [
        [types.InlineKeyboardButton(text="🎁 Выдать награды", callback_data="m_distribute")],
        [types.InlineKeyboardButton(text="👥 Список игроков", callback_data="m_users_list")],
        [types.InlineKeyboardButton(text="⚙️ Управлять лимитами очередей", callback_data="m_limits_menu")],
         
        [types.InlineKeyboardButton(text="🔒 Блокировка очередей для записи", callback_data="m_lock_menu")],
        
        [types.InlineKeyboardButton(text="✏️ Ред. описание очередей", callback_data="m_edit_desc")],
        [types.InlineKeyboardButton(text="🗓 Расписание объявлений", callback_data="m_schedule")],
         
        [types.InlineKeyboardButton(text="📢 Создать объявление", callback_data="m_announce")],
        
        [types.InlineKeyboardButton(text="➕ Добавить персонажа в очередь (любого)", callback_data="m_force_add")],
        [types.InlineKeyboardButton(text="❌ Удалить персонажа из очереди (любого)", callback_data="m_force_del")],
         
        [types.InlineKeyboardButton(text="📜 Общий Архив выдачи наград", callback_data="m_global_log")],
        [types.InlineKeyboardButton(text="👑 Добавить Мастера", callback_data="m_add_admin_start")],
        [types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def get_back_btn(callback_data="back_to_main"):
    return types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 Назад", callback_data=callback_data)]])

# Клавиатура выбора дней недели
def get_weekdays_kb(selected_days=None):
    if selected_days is None: selected_days = []
    
    # Коды дней для APScheduler
    days = [("Понедельник", "mon"), ("Вторник", "tue"), ("Среда", "wed"), 
            ("Четверг", "thu"), ("Пятница", "fri"), ("Суббота", "sat"), ("Воскресенье", "sun")]
    
    kb = []
    for name, code in days:
        # Если день выбран, ставим галочку
        mark = "✅" if code in selected_days else "⬜"
        kb.append([types.InlineKeyboardButton(text=f"{mark} {name}", callback_data=f"toggle_day_{code}")])
    
    # Кнопка Готово
    kb.append([types.InlineKeyboardButton(text="💾 Готово / Далее", callback_data="days_confirm")])
    return types.InlineKeyboardMarkup(inline_keyboard=kb)