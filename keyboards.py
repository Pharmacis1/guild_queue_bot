from aiogram import types

# --- INLINE KEYBOARDS ---

def get_main_menu(user):
    kb = [
        [types.InlineKeyboardButton(text="👥 Мои персонажи", callback_data="menu_chars")],
        [types.InlineKeyboardButton(text="✍️ Записаться в очередь", callback_data="menu_join")],
        [types.InlineKeyboardButton(text="📜 Моя история получения наград", callback_data="menu_history")],
        [types.InlineKeyboardButton(text="ℹ️ Инфо об очередях", callback_data="menu_info")],
        [types.InlineKeyboardButton(text="🛌 Отсутствие(AFK)", callback_data="menu_afk")],
        [types.InlineKeyboardButton(text="🏃 Управление записями в очереди", callback_data="my_active_queues")]
    ]
    if user.is_master:
        kb.append([types.InlineKeyboardButton(text="👑 Панель Мастера", callback_data="menu_master")])
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def get_unauthorized_menu():
    kb = [
        [types.InlineKeyboardButton(text="➕ Добавить основу", callback_data="add_main")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def get_pending_menu(nick):
    kb = [
        [types.InlineKeyboardButton(text="✏️ Исправить заявку", callback_data="add_main")],
        [types.InlineKeyboardButton(text="❌ Отменить заявку", callback_data="cancel_request")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def get_master_menu():
    kb = [
        [types.InlineKeyboardButton(text="🛡 Управление очередями", callback_data="m_menu_queues")],
        [types.InlineKeyboardButton(text="👥 Сообщество и игроки", callback_data="m_menu_community")],
        [types.InlineKeyboardButton(text="📢 Объявления", callback_data="m_menu_announce")],
        [types.InlineKeyboardButton(text="💾 Система и Бэкапы", callback_data="m_menu_system")],
        [types.InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def get_master_queues_menu():
    kb = [
        [types.InlineKeyboardButton(text="🎁 Выдать награды", callback_data="m_distribute")],
        [types.InlineKeyboardButton(text="➕ Добавить персонажа в очередь (любого)", callback_data="m_force_add")],
        [types.InlineKeyboardButton(text="❌ Удалить персонажа из очереди (любого)", callback_data="m_force_del")],
        [types.InlineKeyboardButton(text="⚙️ Управлять лимитами очередей", callback_data="m_limits_menu")],
        [types.InlineKeyboardButton(text="🔒 Блокировка очередей для записи", callback_data="m_lock_menu")],
        [types.InlineKeyboardButton(text="✏️ Ред. описание очередей", callback_data="m_edit_desc")],
        [types.InlineKeyboardButton(text="🔙 Назад в меню Мастера", callback_data="menu_master")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def get_master_community_menu():
    kb = [
        [types.InlineKeyboardButton(text="👥 Список игроков", callback_data="m_users_list")],
        [types.InlineKeyboardButton(text="🛌 Список AFK", callback_data="m_afk_list")],
        [types.InlineKeyboardButton(text="🔐 Код верификации", callback_data="m_verification")],
        [types.InlineKeyboardButton(text="📜 Общий Архив выдачи наград", callback_data="m_global_log")],
        [types.InlineKeyboardButton(text="🔙 Назад в меню Мастера", callback_data="menu_master")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def get_master_announce_menu():
    kb = [
        [types.InlineKeyboardButton(text="📢 Создать объявление", callback_data="m_announce")],
        [types.InlineKeyboardButton(text="🗓 Расписание объявлений", callback_data="m_schedule")],
        [types.InlineKeyboardButton(text="🔙 Назад в меню Мастера", callback_data="menu_master")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def get_master_system_menu():
    kb = [
        [types.InlineKeyboardButton(text="💾 Скачать Бэкап БД", callback_data="m_backup")],
        [types.InlineKeyboardButton(text="🔙 Назад в меню Мастера", callback_data="menu_master")]
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

# --- REPLY KEYBOARDS (Persistent) ---
def get_persistent_menu():
    kb = [
        [types.KeyboardButton(text="🏠 Главное меню")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_afk_menu(user):
    kb = [
        [types.InlineKeyboardButton(text="🛌 Установить период AFK", callback_data="afk_set")],
        [types.InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
    ]
    if user.afk_start and user.afk_end:
        kb.insert(1, [types.InlineKeyboardButton(text="❌ Снять режим AFK", callback_data="afk_clear")])
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def get_afk_start_kb():
    kb = [
        [types.InlineKeyboardButton(text="Сегодня", callback_data="afk_date_today"),
         types.InlineKeyboardButton(text="Завтра", callback_data="afk_date_tomorrow")],
        [types.InlineKeyboardButton(text="🔙 Отмена", callback_data="menu_afk")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)

def get_afk_end_kb():
    kb = [
        [types.InlineKeyboardButton(text="+3 Дня", callback_data="afk_dur_3"),
         types.InlineKeyboardButton(text="+7 Дней", callback_data="afk_dur_7"),
         types.InlineKeyboardButton(text="+14 Дней", callback_data="afk_dur_14")],
        [types.InlineKeyboardButton(text="До конца месяца", callback_data="afk_dur_month")],
        [types.InlineKeyboardButton(text="🔙 Отмена", callback_data="menu_afk")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=kb)