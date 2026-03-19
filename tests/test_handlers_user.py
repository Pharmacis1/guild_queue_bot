from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from datetime import datetime

from database import Character, User, QueueType, QueueEntry, RewardHistory
from handlers import user as user_handler

# --- Fixtures ---

@pytest.fixture
def mock_message():
    message = AsyncMock(spec=types.Message)
    message.from_user = MagicMock(spec=types.User)
    message.from_user.id = 123456789
    message.from_user.username = "test_user"
    message.chat = MagicMock(spec=types.Chat)
    message.chat.id = 123456789
    message.bot = AsyncMock()
    message.answer = AsyncMock()
    message.reply = AsyncMock()
    message.edit_text = AsyncMock()
    return message

@pytest.fixture
def mock_callback_query():
    cb = AsyncMock(spec=types.CallbackQuery)
    cb.from_user = MagicMock(spec=types.User)
    cb.from_user.id = 123456789
    cb.from_user.username = "test_user"
    cb.message = AsyncMock(spec=types.Message)
    cb.message.chat = MagicMock(spec=types.Chat)
    cb.message.chat.id = 123456789
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.bot = AsyncMock()
    return cb

@pytest.fixture
def mock_state():
    state = AsyncMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={})
    return state

# --- Tests ---

@pytest.mark.asyncio
async def test_cmd_start_new_user(async_test_session, mock_message):
    """Test /start command for a completely new user."""
    await user_handler.cmd_start(mock_message, session=async_test_session)

    result = await async_test_session.execute(select(User).filter_by(telegram_id=123456789))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.username == "test_user"
    assert mock_message.answer.called

@pytest.mark.asyncio
async def test_cmd_start_existing_user(async_test_session, mock_message):
    """Test /start for existing user with Main Character."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    char = Character(user_id=user.id, nickname="MainChar", is_main=True)
    async_test_session.add(char)
    await async_test_session.commit()

    await user_handler.cmd_start(mock_message, session=async_test_session)
    
    found_menu = False
    for call in mock_message.answer.call_args_list:
        args, _ = call
        if args and "Выбери действие" in args[0]:
            found_menu = True
    assert found_menu

@pytest.mark.asyncio
async def test_process_main_input_entry_success(async_test_session, mock_message, mock_state):
    """Test adding a main character successfully."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.commit()

    mock_message.text = "NewMain"
    with patch("handlers.user.check_google_sheet", new=AsyncMock(return_value=True)):
        with patch("handlers.user.get_setting", new=AsyncMock(return_value=None)):
            await user_handler.process_main_input_entry(mock_message, mock_state, session=async_test_session)

    result = await async_test_session.execute(select(Character).filter_by(nickname="NewMain"))
    char = result.scalar_one_or_none()
    assert char is not None
    assert char.user_id == user.id
    assert char.is_main is True
    assert "Основа сохранена" in mock_message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_chars_menu(async_test_session, mock_callback_query):
    """Test displaying the characters menu."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.commit()

    with patch("handlers.user.get_menu_text", new=AsyncMock(return_value=("Custom Title:", False))):
        await user_handler.chars_menu(mock_callback_query, session=async_test_session)

    assert mock_callback_query.message.edit_text.called
    assert "Custom Title:" in mock_callback_query.message.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_add_main_start(mock_callback_query, mock_state):
    """Test entering the state to add a main character."""
    await user_handler.add_main_start(mock_callback_query, mock_state)
    assert mock_callback_query.message.edit_text.called
    assert "Введи никнейм" in mock_callback_query.message.edit_text.call_args[0][0]
    assert mock_state.set_state.called

@pytest.mark.asyncio
async def test_add_alt_start(mock_callback_query, mock_state):
    """Test entering the state to add an alt character."""
    await user_handler.add_alt_start(mock_callback_query, mock_state)
    assert mock_callback_query.message.edit_text.called
    assert "Введи никнейм" in mock_callback_query.message.edit_text.call_args[0][0]
    assert mock_state.set_state.called

@pytest.mark.asyncio
async def test_process_main_input_entry_unknown_no_code(async_test_session, mock_message, mock_state):
    """Test process_main_input_entry when nick is unknown and no code is required."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.commit()
    mock_message.text = "UnknownMain"

    with patch("handlers.user.check_google_sheet", new=AsyncMock(return_value=False)):
        with patch("handlers.user.get_setting", new=AsyncMock(return_value=None)):
            with patch("handlers.user.send_approval_request", new=AsyncMock()) as mock_approval:
                await user_handler.process_main_input_entry(mock_message, mock_state, session=async_test_session)
                assert mock_approval.called

@pytest.mark.asyncio
async def test_process_main_input_entry_with_code(async_test_session, mock_message, mock_state):
    """Test process_main_input_entry when code is required."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.commit()
    mock_message.text = "CodeMain"

    with patch("handlers.user.check_google_sheet", new=AsyncMock(return_value=True)):
        with patch("handlers.user.get_setting", new=AsyncMock(return_value="SecretCode")):
            await user_handler.process_main_input_entry(mock_message, mock_state, session=async_test_session)
            assert mock_state.set_state.called
            assert "Введите код верификации" in mock_message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_process_verification_code_success(async_test_session, mock_message, mock_state):
    """Test process_verification_code with correct code."""
    mock_message.text = "SecretCode"
    mock_state.get_data = AsyncMock(return_value={"temp_nick": "VerifMain", "temp_action": "main_input", "needs_approval": False})

    with patch("handlers.user.get_setting", new=AsyncMock(return_value="SecretCode")):
        with patch("handlers.user.finish_main_input", new=AsyncMock()) as mock_finish:
            await user_handler.process_verification_code(mock_message, mock_state, session=async_test_session)
            assert mock_finish.called

@pytest.mark.asyncio
async def test_process_verification_code_fail(async_test_session, mock_message, mock_state):
    """Test process_verification_code with incorrect code."""
    mock_message.text = "WrongCode"
    with patch("handlers.user.get_setting", new=AsyncMock(return_value="SecretCode")):
        await user_handler.process_verification_code(mock_message, mock_state, session=async_test_session)
        assert "Неверный код" in mock_message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_del_alt_menu(async_test_session, mock_callback_query):
    """Test del_alt_menu character list presentation."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    char = Character(user_id=user.id, nickname="AltChar", is_main=False)
    async_test_session.add(char)
    await async_test_session.commit()

    await user_handler.del_alt_menu(mock_callback_query, session=async_test_session)
    assert "AltChar" in str(mock_callback_query.message.edit_text.call_args[1].get("reply_markup").model_dump())

@pytest.mark.asyncio
async def test_del_char_action_with_queues(async_test_session, mock_callback_query):
    """Test del_char_action when character is in queues."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    alt_char = Character(user_id=user.id, nickname="AltChar", is_main=False)
    main_char = Character(user_id=user.id, nickname="MainChar", is_main=True)
    async_test_session.add_all([alt_char, main_char])
    await async_test_session.flush()
    q_type = QueueType(name="TestQ", is_active=True)
    async_test_session.add(q_type)
    await async_test_session.flush()
    entry = QueueEntry(queue_type_id=q_type.id, user_id=user.id, character_name="AltChar")
    async_test_session.add(entry)
    await async_test_session.commit()

    mock_callback_query.data = f"del_c_{alt_char.id}"
    await user_handler.del_char_action(mock_callback_query, session=async_test_session)
    assert "записан в очередях" in mock_callback_query.message.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_del_char_action_no_queues(async_test_session, mock_callback_query):
    """Test del_char_action when character is NOT in queues."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    alt_char = Character(user_id=user.id, nickname="AltChar2", is_main=False)
    async_test_session.add(alt_char)
    await async_test_session.commit()

    mock_callback_query.data = f"del_c_{alt_char.id}"
    with patch("handlers.user.del_alt_menu", new=AsyncMock()):
        with patch("handlers.user.get_setting", new=AsyncMock(return_value=None)):
            await user_handler.del_char_action(mock_callback_query, session=async_test_session)
    
    char = await async_test_session.get(Character, alt_char.id)
    assert char is None
    assert "удален" in mock_callback_query.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_join_menu(async_test_session, mock_callback_query):
    """Test listing of queues in the join menu."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    q1 = QueueType(name="Queue A", is_active=True)
    q2 = QueueType(name="Queue B", is_active=True)
    async_test_session.add_all([q1, q2])
    await async_test_session.commit()

    with patch("handlers.user.get_menu_text", new=AsyncMock(return_value=("Custom Title:", False))):
        await user_handler.join_menu(mock_callback_query, session=async_test_session)

    kb_str = str(mock_callback_query.message.edit_text.call_args[1].get("reply_markup").model_dump())
    assert "Queue A" in kb_str
    assert "Queue B" in kb_str

@pytest.mark.asyncio
async def test_view_queue(async_test_session, mock_callback_query):
    """Test viewing a specific queue."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    q = QueueType(name="Test Queue", is_active=True, description="Test Desc")
    async_test_session.add(q)
    await async_test_session.commit()

    mock_callback_query.data = f"view_q_{q.id}"
    await user_handler.view_queue(mock_callback_query, session=async_test_session)
    assert "Test Queue" in mock_callback_query.message.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_pre_join(async_test_session, mock_callback_query):
    """Test character selection for pre_join."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    q = QueueType(name="Test Queue", is_active=True)
    char = Character(user_id=user.id, nickname="JoinChar", is_main=True)
    async_test_session.add_all([q, char])
    await async_test_session.commit()

    mock_callback_query.data = f"pre_join_{q.id}_auto"
    await user_handler.pre_join(mock_callback_query, session=async_test_session)
    assert "Кем записаться" in mock_callback_query.message.edit_text.call_args[0][0]
    assert "JoinChar" in str(mock_callback_query.message.edit_text.call_args[1].get("reply_markup").model_dump())

@pytest.mark.asyncio
async def test_join_final(async_test_session, mock_callback_query):
    """Test joining a queue."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    q = QueueType(name="Test Queue", is_active=True)
    char = Character(user_id=user.id, nickname="JoinChar", is_main=True)
    async_test_session.add_all([q, char])
    await async_test_session.commit()

    mock_callback_query.data = f"join_final_{q.id}_{char.id}_auto"
    entry = QueueEntry(queue_type_id=q.id, user_id=user.id, character_name="JoinChar")
    async_test_session.add(entry)
    await async_test_session.commit()

    with patch("handlers.user.join_queue", new=AsyncMock(return_value=(True, "Success", entry))):
        with patch("handlers.user.log_reward_to_sheet", new=AsyncMock()):
            with patch("handlers.user.view_queue", new=AsyncMock()):
                await user_handler.join_final(mock_callback_query, session=async_test_session)
    
    assert "Success" in mock_callback_query.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_leave_queue_handler(async_test_session, mock_callback_query):
    """Test leaving a queue."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    q = QueueType(name="Test Queue", is_active=True)
    async_test_session.add(q)
    await async_test_session.commit()

    mock_callback_query.data = f"leave_q_{q.id}"
    with patch("handlers.user.leave_queue", new=AsyncMock(return_value=(True, "Left", MagicMock(character_name="LeftChar")))):
        with patch("handlers.user.log_reward_to_sheet", new=AsyncMock()):
            with patch("handlers.user.view_queue", new=AsyncMock()):
                await user_handler.leave_queue_handler(mock_callback_query, session=async_test_session)
    assert "Left" in mock_callback_query.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_show_my_active_queues(async_test_session, mock_callback_query):
    """Test viewing active queues."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    q = QueueType(name="Test Queue", is_active=True)
    async_test_session.add(q)
    await async_test_session.flush()
    entry = QueueEntry(queue_type_id=q.id, user_id=user.id, character_name="MyChar", auto_requeue=True)
    async_test_session.add(entry)
    await async_test_session.commit()

    await user_handler.show_my_active_queues(mock_callback_query, session=async_test_session)
    assert "Test Queue" in mock_callback_query.message.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_toggle_mode_handler(async_test_session, mock_callback_query):
    """Test toggling auto/once mode in an active queue."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    q = QueueType(name="Test Queue", is_active=True)
    async_test_session.add(q)
    await async_test_session.flush()
    entry = QueueEntry(queue_type_id=q.id, user_id=user.id, character_name="MyChar", auto_requeue=False)
    async_test_session.add(entry)
    await async_test_session.commit()

    mock_callback_query.data = f"toggle_mode_{entry.id}"
    with patch("handlers.user.show_my_active_queues", new=AsyncMock()):
        await user_handler.toggle_mode_handler(mock_callback_query, session=async_test_session)

    await async_test_session.refresh(entry)
    assert entry.auto_requeue is True

@pytest.mark.asyncio
async def test_swap_start(async_test_session, mock_callback_query):
    """Test swap_start displays character options."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    char1 = Character(user_id=user.id, nickname="Char1", is_main=True)
    char2 = Character(user_id=user.id, nickname="Char2", is_main=False)
    q = QueueType(name="Test Queue", is_active=True)
    async_test_session.add_all([char1, char2, q])
    await async_test_session.flush()
    entry = QueueEntry(queue_type_id=q.id, user_id=user.id, character_name="Char1")
    async_test_session.add(entry)
    await async_test_session.commit()

    mock_callback_query.data = f"swap_start_{entry.id}"
    await user_handler.swap_start(mock_callback_query, session=async_test_session)
    assert "Char2" in str(mock_callback_query.message.edit_text.call_args[1].get("reply_markup").model_dump())

@pytest.mark.asyncio
async def test_do_swap_finish(async_test_session, mock_callback_query):
    """Test do_swap_finish switches characters in queue."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    char1 = Character(user_id=user.id, nickname="Char1", is_main=True)
    char2 = Character(user_id=user.id, nickname="Char2", is_main=False)
    q = QueueType(name="Test Queue", is_active=True)
    async_test_session.add_all([char1, char2, q])
    await async_test_session.flush()
    entry = QueueEntry(queue_type_id=q.id, user_id=user.id, character_name="Char1")
    async_test_session.add(entry)
    await async_test_session.commit()

    mock_callback_query.data = f"do_swap_{entry.id}_{char2.id}"
    with patch("handlers.user.log_reward_to_sheet", new=AsyncMock()):
        with patch("handlers.user.show_my_active_queues", new=AsyncMock()):
            await user_handler.do_swap_finish(mock_callback_query, session=async_test_session)

    await async_test_session.refresh(entry)
    assert entry.character_name == "Char2"

@pytest.mark.asyncio
async def test_afk_menu(async_test_session, mock_callback_query, mock_state):
    """Test afk_menu display."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.commit()

    await user_handler.afk_menu(mock_callback_query, mock_state, session=async_test_session)
    assert "AFK" in mock_callback_query.message.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_afk_clear(async_test_session, mock_callback_query):
    """Test afk_clear removes AFK status."""
    user = User(telegram_id=123456789, username="test_user", afk_start=datetime.now(), afk_end=datetime.now())
    async_test_session.add(user)
    await async_test_session.commit()

    with patch("handlers.user.afk_menu", new=AsyncMock()):
        await user_handler.afk_clear(mock_callback_query, session=async_test_session)

    await async_test_session.refresh(user)
    assert user.afk_start is None
    assert user.afk_end is None

@pytest.mark.asyncio
async def test_cancel_pending_request(async_test_session, mock_callback_query, mock_state):
    """Test cancel_pending_request."""
    user = User(telegram_id=123456789, username="test_user", pending_request_nick="PendingChar")
    async_test_session.add(user)
    await async_test_session.commit()

    with patch("handlers.user.cmd_start", new=AsyncMock()):
        await user_handler.cancel_pending_request(mock_callback_query, mock_state, session=async_test_session)

    await async_test_session.refresh(user)
    assert user.pending_request_nick is None

@pytest.mark.asyncio
async def test_my_history(async_test_session, mock_callback_query):
    """Test my_history display."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    hist = RewardHistory(user_id=user.id, queue_name="TestQ", character_name="Char", timestamp=datetime.now())
    async_test_session.add(hist)
    await async_test_session.commit()

    await user_handler.my_history(mock_callback_query, session=async_test_session)
    assert "История наград" in mock_callback_query.message.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_menu_info(async_test_session, mock_callback_query):
    """Test menu_info display."""
    await user_handler.info_queues(mock_callback_query)
    assert "Справка" in mock_callback_query.message.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_back_to_menu(async_test_session, mock_callback_query, mock_state):
    """Test returning to the main menu."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.commit()

    with patch("handlers.user.get_menu_text", new=AsyncMock(return_value=("Main Menu Text", False))):
        await user_handler.back_to_menu(mock_callback_query, mock_state, session=async_test_session)
        
    assert mock_state.clear.called
    assert "Main Menu Text" in mock_callback_query.message.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_finish_main_input_merge_stub(async_test_session, mock_message, mock_state):
    """Test finish_main_input merging a stub user into the real user."""
    real_user = User(telegram_id=123456789, username="real_user")
    stub_user = User(telegram_id=None, username="stub_user")
    async_test_session.add_all([real_user, stub_user])
    await async_test_session.flush()
    char = Character(user_id=stub_user.id, nickname="MergeChar", is_main=True)
    async_test_session.add(char)
    await async_test_session.commit()

    mock_state.get_data = AsyncMock(return_value={"temp_nick": "MergeChar", "temp_action": "main_input"})
    mock_message.text = "MergeChar"

    with patch("handlers.user.get_menu_text", new=AsyncMock(return_value=("Menu", False))):
        await user_handler.finish_main_input(mock_message, mock_state, session=async_test_session)

    await async_test_session.refresh(char)
    assert char.user_id == real_user.id
    stub_db = await async_test_session.get(User, stub_user.id)
    assert stub_db is None

@pytest.mark.asyncio
async def test_process_alt_input_entry_is_known_no_code(async_test_session, mock_message, mock_state):
    """Test process_alt_input_entry when nick is known and no code required."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.commit()
    mock_message.text = "AltKnown"

    with patch("handlers.user.check_google_sheet", new=AsyncMock(return_value=True)):
        with patch("handlers.user.get_setting", new=AsyncMock(return_value=None)):
            with patch("handlers.user.finish_alt_input", new=AsyncMock()) as mock_finish:
                await user_handler.process_alt_input_entry(mock_message, mock_state, session=async_test_session)
                assert mock_finish.called

@pytest.mark.asyncio
async def test_finish_alt_input_success(async_test_session, mock_message, mock_state):
    """Test finish_alt_input successfully adding an alt."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    main_char = Character(user_id=user.id, nickname="MainChar", is_main=True)
    async_test_session.add(main_char)
    await async_test_session.commit()

    mock_message.text = "AltChar"
    with patch("handlers.user.get_menu_text", new=AsyncMock(return_value=("Menu Text", False))):
        await user_handler.finish_alt_input(mock_message, mock_state, session=async_test_session)

    result = await async_test_session.execute(select(Character).filter_by(nickname="AltChar"))
    char = result.scalar_one_or_none()
    assert char is not None
    assert char.user_id == user.id
    assert not char.is_main

@pytest.mark.asyncio
async def test_finish_alt_input_no_main(async_test_session, mock_message, mock_state):
    """Test finish_alt_input failing due to no main character."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.commit()
    
    mock_message.text = "AltChar"
    await user_handler.finish_alt_input(mock_message, mock_state, session=async_test_session)
    assert "Сначала добавь" in mock_message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_afk_set_start(mock_callback_query, mock_state):
    """Test afk_set_start starts AFK date entry FSM."""
    await user_handler.afk_set_start(mock_callback_query, mock_state)
    assert mock_state.set_state.called
    assert "Дата НАЧАЛА" in mock_callback_query.message.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_afk_start_quick(mock_callback_query, mock_state):
    """Test afk_start_quick predefined dates."""
    mock_callback_query.data = "afk_date_today"
    with patch("handlers.user.ask_afk_end", new=AsyncMock()) as mock_ask:
        await user_handler.afk_start_quick(mock_callback_query, mock_state)
        assert mock_ask.called
        assert mock_state.update_data.called

@pytest.mark.asyncio
async def test_afk_start_manual(mock_message, mock_state):
    """Test afk_start_manual with specific date text."""
    mock_message.text = "12/03"
    with patch("handlers.user.parse_date_input", return_value=datetime(2026, 3, 12)):
        with patch("handlers.user.ask_afk_end", new=AsyncMock()) as mock_ask:
            await user_handler.afk_start_manual(mock_message, mock_state)
            assert mock_ask.called
            assert mock_state.update_data.called

@pytest.mark.asyncio
async def test_afk_end_quick(mock_callback_query, mock_state):
    """Test afk_end_quick predefined end date."""
    mock_callback_query.data = "afk_dur_month"
    mock_state.get_data = AsyncMock(return_value={"start_date": datetime(2026, 3, 1)})
    
    await user_handler.afk_end_quick(mock_callback_query, mock_state)
    assert mock_callback_query.message.edit_text.called
    assert mock_state.update_data.called

@pytest.mark.asyncio
async def test_afk_end_manual(mock_message, mock_state):
    """Test afk_end_manual with specific date text."""
    mock_state.get_data = AsyncMock(return_value={"start_date": datetime(2026, 3, 1)})
    mock_message.text = "15/03"
    with patch("handlers.user.parse_date_input", return_value=datetime(2026, 3, 15)):
        await user_handler.afk_end_manual(mock_message, mock_state)
        assert mock_message.answer.called
        assert mock_state.update_data.called

@pytest.mark.asyncio
async def test_finish_afk_setup(async_test_session, mock_message, mock_state):
    """Test finish_afk_setup saves to DB and logs history."""
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.commit()

    start = datetime(2026, 3, 12)
    end = datetime(2026, 3, 15)

    with patch("handlers.user.get_afk_menu", new=AsyncMock(return_value=None)):
        await user_handler.finish_afk_setup(mock_message, mock_state, start, end, None, session=async_test_session)
        
        await async_test_session.refresh(user)
        assert user.afk_start is not None
        assert user.afk_end is not None

@pytest.mark.asyncio
async def test_send_approval_request(async_test_session, mock_message, mock_state):
    """Test send_approval_request sends to master."""
    user = User(telegram_id=123456789, username="test_user")
    master = User(telegram_id=987654321, username="master", is_master=True)
    async_test_session.add_all([user, master])
    await async_test_session.commit()

    with patch("handlers.user.get_menu_text", new=AsyncMock(return_value=("Text", False))):
        await user_handler.send_approval_request(mock_message, mock_state, "NewNick", "main_input", session=async_test_session)

    assert mock_message.bot.send_message.called

@pytest.mark.asyncio
async def test_cmd_get_id(mock_message):
    mock_message.chat.id = -12345
    mock_message.message_thread_id = 6789
    await user_handler.cmd_get_id(mock_message)
    assert mock_message.reply.called
    assert "ID топика: <code>6789</code>" in mock_message.reply.call_args[0][0]

@pytest.mark.asyncio
async def test_group_start_stub(mock_message):
    await user_handler.group_start_stub(mock_message)
    assert mock_message.reply.called
    assert "доступна только в личных" in mock_message.reply.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_start_banned(async_test_session, mock_message):
    user = User(telegram_id=123456789, username="test_user", is_banned=True)
    async_test_session.add(user)
    await async_test_session.commit()
    await user_handler.cmd_start(mock_message, session=async_test_session)
    assert "забанены" in mock_message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_start_pending_request(async_test_session, mock_message):
    user = User(telegram_id=123456789, username="test_user", pending_request_nick="WaitChar")
    async_test_session.add(user)
    await async_test_session.commit()
    await user_handler.cmd_start(mock_message, session=async_test_session)
    assert "Заявка отправлена" in mock_message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_start_heals_main(async_test_session, mock_message):
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    char = Character(user_id=user.id, nickname="AltChar", is_main=False)
    async_test_session.add(char)
    await async_test_session.commit()
    
    with patch("handlers.user.get_menu_text", new=AsyncMock(return_value=("Text", False))):
        await user_handler.cmd_start(mock_message, session=async_test_session)
        
    await async_test_session.refresh(char)
    assert char.is_main is True

@pytest.mark.asyncio
async def test_cancel_pending_request_no_nick(async_test_session, mock_callback_query, mock_state):
    user = User(telegram_id=123456789, username="test_user", pending_request_nick=None)
    async_test_session.add(user)
    await async_test_session.commit()
    
    with patch("handlers.user.cmd_start", new=AsyncMock()) as mock_start:
        await user_handler.cancel_pending_request(mock_callback_query, mock_state, session=async_test_session)
        
    assert mock_callback_query.answer.called
    assert mock_start.called

@pytest.mark.asyncio
async def test_main_menu_text(async_test_session, mock_message):
    with patch("handlers.user.cmd_start", new=AsyncMock()) as mock_start:
        await user_handler.main_menu_text(mock_message, session=async_test_session)
        assert mock_start.called

@pytest.mark.asyncio
async def test_confirm_del_char_complex_swap(async_test_session, mock_callback_query):
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    main_char = Character(user_id=user.id, nickname="MainChar", is_main=True)
    alt_char = Character(user_id=user.id, nickname="AltChar", is_main=False)
    async_test_session.add_all([main_char, alt_char])
    await async_test_session.flush()
    queue = QueueType(name="TestQ", is_active=True)
    async_test_session.add(queue)
    await async_test_session.flush()
    entry = QueueEntry(queue_type_id=queue.id, user_id=user.id, character_name="AltChar")
    async_test_session.add(entry)
    await async_test_session.commit()
    
    mock_callback_query.data = f"conf_del_{alt_char.id}_swap"
    with patch("handlers.user.log_reward_to_sheet", new=AsyncMock()):
        await user_handler.confirm_del_char_complex(mock_callback_query, session=async_test_session)
        
    char_db = await async_test_session.get(Character, alt_char.id)
    assert char_db is None
    await async_test_session.refresh(entry)
    assert entry.character_name == "MainChar"

@pytest.mark.asyncio
async def test_confirm_del_char_complex_kill(async_test_session, mock_callback_query):
    user = User(telegram_id=123456789, username="test_user")
    async_test_session.add(user)
    await async_test_session.flush()
    alt_char = Character(user_id=user.id, nickname="AltChar", is_main=False)
    async_test_session.add(alt_char)
    await async_test_session.flush()
    queue = QueueType(name="TestQ", is_active=True)
    async_test_session.add(queue)
    await async_test_session.flush()
    entry = QueueEntry(queue_type_id=queue.id, user_id=user.id, character_name="AltChar")
    async_test_session.add(entry)
    await async_test_session.commit()
    
    mock_callback_query.data = f"conf_del_{alt_char.id}_kill"
    with patch("handlers.user.log_reward_to_sheet", new=AsyncMock()):
        await user_handler.confirm_del_char_complex(mock_callback_query, session=async_test_session)
        
    char_db = await async_test_session.get(Character, alt_char.id)
    assert char_db is None
    entry_db = await async_test_session.get(QueueEntry, entry.id)
    assert entry_db is None

@pytest.mark.asyncio
async def test_process_alt_input_entry_is_unknown_with_code(async_test_session, mock_message, mock_state):
    """Test process_alt_input_entry when nick is unknown and code is required."""
    mock_message.text = "AltUnknown"
    with patch("handlers.user.check_google_sheet", new=AsyncMock(return_value=False)):
        with patch("handlers.user.get_setting", new=AsyncMock(return_value="1234")):
            await user_handler.process_alt_input_entry(mock_message, mock_state, session=async_test_session)
            assert "Возможно," in mock_message.answer.call_args[0][0]
            assert mock_state.set_state.called

def test_parse_date_input():
    from handlers.user import parse_date_input
    dt1 = parse_date_input("16.03")
    assert dt1 is not None and dt1.day == 16 and dt1.month == 3
    dt2 = parse_date_input("15.01.25")
    assert dt2 is not None and dt2.day == 15 and dt2.month == 1 and dt2.year == 2025
    dt3 = parse_date_input("20.12.2024")
    assert dt3 is not None and dt3.day == 20 and dt3.month == 12 and dt3.year == 2024
    assert parse_date_input("invalid.date") is None
    assert parse_date_input("99.99") is None
