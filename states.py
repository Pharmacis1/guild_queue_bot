from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    waiting_for_main_nickname = State()
    waiting_for_alt_nickname = State()
    waiting_for_main_confirm = State()
    waiting_for_code = State()


class EditQueueStates(StatesGroup):
    waiting_for_new_description = State()


class MasterManageStates(StatesGroup):
    waiting_for_nickname_add = State()
    waiting_for_queue_add = State()
    waiting_for_admin_username = State()
    waiting_for_code_setting = State()
    waiting_for_approve_edit = State()
    waiting_for_rename = State()
    waiting_for_afk_start = State()
    waiting_for_afk_end = State()
    waiting_for_bulk_list = State()
    waiting_for_mode = State()
    waiting_for_log_channel_id = State()


class AnnounceStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_type = State()
    waiting_for_datetime = State()  # Для разового в будущем
    waiting_for_time_only = State()  # Для ежедневного/еженедельного
    waiting_for_days = State()  # Выбор дней недели


class LimitStates(StatesGroup):
    waiting_for_global_limit = State()
    waiting_for_nick_limit = State()
    waiting_for_personal_limit_value = State()


class AFKState(StatesGroup):
    waiting_for_start = State()
    waiting_for_end = State()


class AIAdminStates(StatesGroup):
    waiting_for_topic = State()
    waiting_for_content = State()
    waiting_for_edit_content = State()
    waiting_for_summary_channel = State()

