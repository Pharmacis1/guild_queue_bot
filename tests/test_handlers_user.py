from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import types
from aiogram.fsm.context import FSMContext

from database import Character, User
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

    # Explicitly make async methods AsyncMock
    message.answer = AsyncMock()
    message.reply = AsyncMock()
    message.edit_text = AsyncMock()
    return message


@pytest.fixture
def mock_state():
    state = AsyncMock(spec=FSMContext)
    return state


@pytest.fixture
def sync_test_session(test_db_session):
    """
    Creates a synchronous SQLAlchemy session bound to the test database.
    Patches `handlers.user.session` to use this test session.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Connect to the temp DB path provided by fixture
    engine = create_engine(f"sqlite:///{test_db_session}")
    # Ensure tables exist (normally done by test_db_session fixture but let's be sure if using pure sqlite there)
    # The `test_db_session` fixture in conftest.py already runs Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    # PATCH the session in the handler module AND the original database module
    with patch("database.session", session), patch("handlers.user.session", session):
        yield session

    session.close()


# --- Tests ---


@pytest.mark.asyncio
async def test_cmd_start_new_user(sync_test_session, mock_message):
    """Test /start command for a completely new user."""
    # Execute
    await user_handler.cmd_start(mock_message)

    # Verify User created in DB
    user = sync_test_session.query(User).filter_by(telegram_id=123456789).first()
    assert user is not None, "User was not created in the session!"
    assert user.username == "test_user"

    # Verify Welcome Message
    assert mock_message.answer.called

    calls = mock_message.answer.call_args_list

    # We expect "Добро пожаловать" logic
    found = False
    for call in calls:
        args, kwargs = call
        text = args[0] if args else ""
        if "Добро пожаловать" in text or "Добавить основу" in str(kwargs.get("reply_markup", "")):
            found = True
    assert found, "Welcome message not found in calls"


@pytest.mark.asyncio
async def test_cmd_start_existing_user(sync_test_session, mock_message):
    """Test /start for existing user with Main Character."""
    # Setup Data
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    char = Character(user_id=user.id, nickname="MainChar", is_main=True)
    sync_test_session.add(char)
    sync_test_session.commit()

    # Execute
    await user_handler.cmd_start(mock_message)

    # Verify Main Menu
    calls = mock_message.answer.call_args_list

    found_menu = False
    for call in calls:
        args, kwargs = call
        text = args[0] if args else ""
        # Check text (from get_menu_text) or markup
        if "Выбери действие" in text:
            found_menu = True

    assert found_menu, "Main menu text not found"


@pytest.mark.asyncio
async def test_process_main_input_entry_success(sync_test_session, mock_message, mock_state):
    """Test adding a main character successfully."""
    # Setup User
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    # Mock Message Text (Nickname)
    mock_message.text = "NewMain"

    # Mock check_google_sheet to return True (Known)
    with patch("handlers.user.check_google_sheet", new=AsyncMock(return_value=True)):
        # Mock get_setting to return None (No code required)
        with patch("handlers.user.get_setting", return_value=None):
            # Execute
            await user_handler.process_main_input_entry(mock_message, mock_state)

    # Verify DB
    char = sync_test_session.query(Character).filter_by(nickname="NewMain").first()
    assert char is not None
    assert char.user_id == user.id
    assert char.is_main is True

    # Verify Success Message
    assert mock_message.answer.called
    args, _ = mock_message.answer.call_args
    assert "Основа сохранена" in args[0]

    # Verify State Cleared
    assert mock_state.clear.called

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
    return cb

@pytest.mark.asyncio
async def test_chars_menu(sync_test_session, mock_callback_query):
    """Test displaying the characters menu."""
    # Setup Data
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    with patch("handlers.user.get_menu_text", return_value=("Custom Title:", False)):
        await user_handler.chars_menu(mock_callback_query)

    assert mock_callback_query.message.edit_text.called
    args, kwargs = mock_callback_query.message.edit_text.call_args
    assert "Custom Title:" in args[0]
    markup = kwargs.get("reply_markup")
    assert markup is not None
    # Check buttons
    keyboard_text = str(markup.model_dump())
    assert "add_main" in keyboard_text
    assert "add_alt" in keyboard_text
    assert "del_alt_menu" in keyboard_text

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
async def test_process_main_input_entry_unknown_no_code(sync_test_session, mock_message, mock_state):
    """Test process_main_input_entry when nick is unknown and no code is required (should send to master)."""
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    mock_message.text = "UnknownMain"

    with patch("handlers.user.check_google_sheet", new=AsyncMock(return_value=False)):
        with patch("handlers.user.get_setting", return_value=None):
            with patch("handlers.user.send_approval_request", new=AsyncMock()) as mock_approval:
                await user_handler.process_main_input_entry(mock_message, mock_state)
                
                assert mock_approval.called
                args, _ = mock_approval.call_args
                assert args[2] == "UnknownMain"
                assert args[3] == "main_input"

@pytest.mark.asyncio
async def test_process_main_input_entry_with_code(sync_test_session, mock_message, mock_state):
    """Test process_main_input_entry when code is required."""
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    mock_message.text = "CodeMain"

    with patch("handlers.user.check_google_sheet", new=AsyncMock(return_value=True)):
        with patch("handlers.user.get_setting", return_value="SecretCode"):
            await user_handler.process_main_input_entry(mock_message, mock_state)
            
            # Should ask for code
            assert mock_state.set_state.called
            assert "Введите код верификации" in mock_message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_process_verification_code_success(sync_test_session, mock_message, mock_state):
    """Test process_verification_code with correct code."""
    mock_message.text = "SecretCode"
    mock_state.get_data = AsyncMock(return_value={"temp_nick": "VerifMain", "temp_action": "main_input", "needs_approval": False})

    with patch("handlers.user.get_setting", return_value="SecretCode"):
        with patch("handlers.user.finish_main_input", new=AsyncMock()) as mock_finish:
            await user_handler.process_verification_code(mock_message, mock_state)
            assert mock_finish.called
            args, kwargs = mock_finish.call_args
            assert kwargs.get("nick_override") == "VerifMain"

@pytest.mark.asyncio
async def test_process_verification_code_fail(mock_message, mock_state):
    """Test process_verification_code with incorrect code."""
    mock_message.text = "WrongCode"
    with patch("handlers.user.get_setting", return_value="SecretCode"):
        await user_handler.process_verification_code(mock_message, mock_state)
        assert mock_message.answer.called
        assert "Неверный код" in mock_message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_del_alt_menu(sync_test_session, mock_callback_query):
    """Test del_alt_menu character list presentation."""
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()
    
    char = Character(user_id=user.id, nickname="AltChar", is_main=False)
    sync_test_session.add(char)
    sync_test_session.commit()

    await user_handler.del_alt_menu(mock_callback_query)

    assert mock_callback_query.message.edit_text.called
    markup = mock_callback_query.message.edit_text.call_args[1].get("reply_markup")
    assert "AltChar" in str(markup.model_dump())

@pytest.mark.asyncio
async def test_del_char_action_with_queues(sync_test_session, mock_callback_query):
    """Test del_char_action when character is in queues."""
    from database import QueueType, QueueEntry
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    alt_char = Character(user_id=user.id, nickname="AltChar", is_main=False)
    main_char = Character(user_id=user.id, nickname="MainChar", is_main=True)
    sync_test_session.add(alt_char)
    sync_test_session.add(main_char)
    sync_test_session.commit()

    q_type = QueueType(name="TestQ", is_active=True)
    sync_test_session.add(q_type)
    sync_test_session.commit()

    entry = QueueEntry(queue_type_id=q_type.id, user_id=user.id, character_name="AltChar")
    sync_test_session.add(entry)
    sync_test_session.commit()

    mock_callback_query.data = f"del_c_{alt_char.id}"

    await user_handler.del_char_action(mock_callback_query)
    
    assert mock_callback_query.message.edit_text.called
    assert "записан в очередях" in mock_callback_query.message.edit_text.call_args[0][0]
    assert "Заменить" in str(mock_callback_query.message.edit_text.call_args[1].get("reply_markup").model_dump())

@pytest.mark.asyncio
async def test_del_char_action_no_queues(sync_test_session, mock_callback_query):
    """Test del_char_action when character is NOT in queues."""
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    alt_char = Character(user_id=user.id, nickname="AltChar2", is_main=False)
    sync_test_session.add(alt_char)
    sync_test_session.commit()

    mock_callback_query.data = f"del_c_{alt_char.id}"

    # Also mock del_alt_menu so it doesn't try to render the menu after delete
    with patch("handlers.user.del_alt_menu", new=AsyncMock()):
        with patch("handlers.user.get_setting", return_value=None):
            await user_handler.del_char_action(mock_callback_query)
    
    # Char should be deleted
    assert sync_test_session.get(Character, alt_char.id) is None
    assert mock_callback_query.answer.called
    assert "удален" in mock_callback_query.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_join_menu(sync_test_session, mock_callback_query):
    """Test listing of queues in the join menu."""
    from database import QueueType
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    q1 = QueueType(name="Queue A", is_active=True, description="Desc A")
    q2 = QueueType(name="Queue B", is_active=True, description="Desc B")
    sync_test_session.add_all([q1, q2])
    sync_test_session.commit()

    with patch("handlers.user.get_menu_text", return_value=("Custom Title:", False)):
        await user_handler.join_menu(mock_callback_query)

    assert mock_callback_query.message.edit_text.called
    markup = mock_callback_query.message.edit_text.call_args[1].get("reply_markup")
    kb_str = str(markup.model_dump())
    assert "Queue A" in kb_str
    assert "Queue B" in kb_str

@pytest.mark.asyncio
async def test_view_queue(sync_test_session, mock_callback_query):
    """Test viewing a specific queue."""
    from database import QueueType
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    q = QueueType(name="Test Queue", is_active=True, description="Test Desc")
    sync_test_session.add(q)
    sync_test_session.commit()

    mock_callback_query.data = f"view_q_{q.id}"

    await user_handler.view_queue(mock_callback_query)

    assert mock_callback_query.message.edit_text.called
    args, kwargs = mock_callback_query.message.edit_text.call_args
    assert "Test Queue" in args[0]
    kb_str = str(kwargs.get("reply_markup").model_dump())
    assert "Разово" in kb_str
    assert "Авто" in kb_str

@pytest.mark.asyncio
async def test_pre_join(sync_test_session, mock_callback_query):
    """Test character selection for pre_join."""
    from database import QueueType
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    q = QueueType(name="Test Queue", is_active=True)
    char = Character(user_id=user.id, nickname="JoinChar", is_main=True)
    sync_test_session.add_all([q, char])
    sync_test_session.commit()

    mock_callback_query.data = f"pre_join_{q.id}_auto"

    await user_handler.pre_join(mock_callback_query)

    assert mock_callback_query.message.edit_text.called
    args, kwargs = mock_callback_query.message.edit_text.call_args
    assert "Кем записаться" in args[0]
    kb_str = str(kwargs.get("reply_markup").model_dump())
    assert "JoinChar" in kb_str

@pytest.mark.asyncio
async def test_join_final(sync_test_session, mock_callback_query):
    """Test joining a queue."""
    from database import QueueType
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    q = QueueType(name="Test Queue", is_active=True)
    char = Character(user_id=user.id, nickname="JoinChar", is_main=True)
    sync_test_session.add_all([q, char])
    sync_test_session.commit()

    mock_callback_query.data = f"join_final_{q.id}_{char.id}_auto"

    with patch("handlers.user.join_queue", return_value=(True, "Success", MagicMock(character_name="JoinChar", queue=MagicMock(name="Test Queue")))):
        with patch("handlers.user.log_reward_to_sheet", new=AsyncMock()):
            with patch("handlers.user.view_queue", new=AsyncMock()):
                await user_handler.join_final(mock_callback_query)
    
    assert mock_callback_query.answer.called
    assert "Success" in mock_callback_query.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_leave_queue_handler(sync_test_session, mock_callback_query):
    """Test leaving a queue."""
    from database import QueueType
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()
    
    q = QueueType(name="Test Queue", is_active=True)
    sync_test_session.add(q)
    sync_test_session.commit()

    mock_callback_query.data = f"leave_q_{q.id}"

    with patch("handlers.user.leave_queue", return_value=(True, "Left", MagicMock(character_name="LeftChar"))):
        with patch("handlers.user.log_reward_to_sheet", new=AsyncMock()):
            with patch("handlers.user.view_queue", new=AsyncMock()):
                await user_handler.leave_queue_handler(mock_callback_query)
                
    assert mock_callback_query.answer.called
    assert "Left" in mock_callback_query.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_show_my_active_queues(sync_test_session, mock_callback_query):
    """Test viewing active queues."""
    from database import QueueType, QueueEntry
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()
    
    q = QueueType(name="Test Queue", is_active=True)
    sync_test_session.add(q)
    sync_test_session.commit()

    entry = QueueEntry(queue_type_id=q.id, user_id=user.id, character_name="MyChar", auto_requeue=True)
    sync_test_session.add(entry)
    sync_test_session.commit()

    await user_handler.show_my_active_queues(mock_callback_query)

    assert mock_callback_query.message.edit_text.called
    args, kwargs = mock_callback_query.message.edit_text.call_args
    assert "Test Queue" in args[0]
    kb_str = str(kwargs.get("reply_markup").model_dump())
    assert "swap" in kb_str
    assert "toggle" in kb_str

@pytest.mark.asyncio
async def test_toggle_mode_handler(sync_test_session, mock_callback_query):
    """Test toggling auto/once mode in an active queue."""
    from database import QueueType, QueueEntry
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()
    
    q = QueueType(name="Test Queue", is_active=True)
    sync_test_session.add(q)
    sync_test_session.commit()

    entry = QueueEntry(queue_type_id=q.id, user_id=user.id, character_name="MyChar", auto_requeue=False)
    sync_test_session.add(entry)
    sync_test_session.commit()

    mock_callback_query.data = f"toggle_mode_{entry.id}"

    with patch("handlers.user.show_my_active_queues", new=AsyncMock()):
        await user_handler.toggle_mode_handler(mock_callback_query)

    # Should toggle from False to True
    updated_entry = sync_test_session.get(QueueEntry, entry.id)
    assert updated_entry.auto_requeue is True
    assert mock_callback_query.answer.called
    assert "Авто" in mock_callback_query.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_swap_start(sync_test_session, mock_callback_query):
    """Test swap_start displays character options."""
    from database import QueueType, QueueEntry
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()
    
    char1 = Character(user_id=user.id, nickname="Char1", is_main=True)
    char2 = Character(user_id=user.id, nickname="Char2", is_main=False)
    q = QueueType(name="Test Queue", is_active=True)
    sync_test_session.add_all([char1, char2, q])
    sync_test_session.commit()

    entry = QueueEntry(queue_type_id=q.id, user_id=user.id, character_name="Char1")
    sync_test_session.add(entry)
    sync_test_session.commit()

    mock_callback_query.data = f"swap_start_{entry.id}"

    await user_handler.swap_start(mock_callback_query)

    assert mock_callback_query.message.edit_text.called
    kb_str = str(mock_callback_query.message.edit_text.call_args[1].get("reply_markup").model_dump())
    assert "Char2" in kb_str

@pytest.mark.asyncio
async def test_do_swap_finish(sync_test_session, mock_callback_query):
    """Test do_swap_finish switches characters in queue."""
    from database import QueueType, QueueEntry
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()
    
    char1 = Character(user_id=user.id, nickname="Char1", is_main=True)
    char2 = Character(user_id=user.id, nickname="Char2", is_main=False)
    q = QueueType(name="Test Queue", is_active=True)
    sync_test_session.add_all([char1, char2, q])
    sync_test_session.commit()

    entry = QueueEntry(queue_type_id=q.id, user_id=user.id, character_name="Char1")
    sync_test_session.add(entry)
    sync_test_session.commit()

    mock_callback_query.data = f"do_swap_{entry.id}_{char2.id}"

    with patch("handlers.user.log_reward_to_sheet", new=AsyncMock()):
        with patch("handlers.user.show_my_active_queues", new=AsyncMock()):
            await user_handler.do_swap_finish(mock_callback_query)

    # Refresh entry and verify
    updated_entry = sync_test_session.get(QueueEntry, entry.id)
    assert updated_entry.character_name == "Char2"
    assert mock_callback_query.answer.called
    assert "Char1 -> Char2" in mock_callback_query.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_afk_menu(sync_test_session, mock_callback_query, mock_state):
    """Test afk_menu display."""
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    await user_handler.afk_menu(mock_callback_query, mock_state)

    assert mock_callback_query.message.edit_text.called
    assert "AFK" in mock_callback_query.message.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_afk_clear(sync_test_session, mock_callback_query):
    """Test afk_clear removes AFK status."""
    from datetime import datetime
    user = User(telegram_id=123456789, username="test_user", afk_start=datetime.now(), afk_end=datetime.now())
    sync_test_session.add(user)
    sync_test_session.commit()

    with patch("handlers.user.afk_menu", new=AsyncMock()):
        await user_handler.afk_clear(mock_callback_query)

    user_db = sync_test_session.get(User, user.id)
    assert user_db.afk_start is None
    assert user_db.afk_end is None
    assert mock_callback_query.answer.called

@pytest.mark.asyncio
async def test_cancel_pending_request(sync_test_session, mock_callback_query, mock_state):
    """Test cancel_pending_request."""
    user = User(telegram_id=123456789, username="test_user", pending_request_nick="PendingChar")
    sync_test_session.add(user)
    sync_test_session.commit()

    with patch("handlers.user.cmd_start", new=AsyncMock()):
        await user_handler.cancel_pending_request(mock_callback_query, mock_state)

    user_db = sync_test_session.get(User, user.id)
    assert user_db.pending_request_nick is None
    assert mock_callback_query.answer.called
    assert "отменена" in mock_callback_query.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_menu_history(sync_test_session, mock_callback_query):
    """Test menu_history display."""
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    from database import RewardHistory
    from datetime import datetime
    hist = RewardHistory(user_id=user.id, queue_name="TestQ", character_name="Char", timestamp=datetime.now())
    sync_test_session.add(hist)
    sync_test_session.commit()

    await user_handler.my_history(mock_callback_query)

    assert mock_callback_query.message.edit_text.called
    assert "История наград" in mock_callback_query.message.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_menu_info(mock_callback_query):
    """Test menu_info display."""
    await user_handler.info_queues(mock_callback_query)

    assert mock_callback_query.message.edit_text.called
    assert "Справка" in mock_callback_query.message.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_back_to_menu(sync_test_session, mock_callback_query, mock_state):
    """Test returning to the main menu."""
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    with patch("handlers.user.get_menu_text", return_value=("Main Menu Text", False)):
        await user_handler.back_to_menu(mock_callback_query, mock_state)
        
    assert mock_state.clear.called
    assert mock_callback_query.message.edit_text.called
    assert "Main Menu Text" in mock_callback_query.message.edit_text.call_args[0][0]

@pytest.mark.asyncio
async def test_finish_main_input_merge_stub(sync_test_session, mock_message, mock_state):
    """Test finish_main_input merging a stub user into the real user."""
    real_user = User(telegram_id=123456789, username="real_user")
    stub_user = User(telegram_id=None, username="stub_user")  # Must be None for merging
    sync_test_session.add_all([real_user, stub_user])
    sync_test_session.commit()

    # Stub character connected to stub user
    char = Character(user_id=stub_user.id, nickname="MergeChar", is_main=True)
    sync_test_session.add(char)
    sync_test_session.commit()

    mock_state.get_data = AsyncMock(return_value={"temp_nick": "MergeChar", "temp_action": "main_input"})
    mock_message.text = "MergeChar"

    with patch("handlers.user.get_menu_text", return_value=("Menu", False)):
        await user_handler.finish_main_input(mock_message, mock_state)

    # Check that character now belongs to real user
    updated_char = sync_test_session.get(Character, char.id)
    assert updated_char.user_id == real_user.id
    
    # Check that stub user was deleted
    assert sync_test_session.get(User, stub_user.id) is None

    assert mock_message.answer.called
    assert "Основа сохранена" in mock_message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_process_alt_input_entry_is_known_no_code(sync_test_session, mock_message, mock_state):
    """Test process_alt_input_entry when nick is known and no code required."""
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()
    mock_message.text = "AltKnown"

    with patch("handlers.user.check_google_sheet", new=AsyncMock(return_value=True)):
        with patch("handlers.user.get_setting", return_value=None):
            with patch("handlers.user.finish_alt_input", new=AsyncMock()) as mock_finish:
                await user_handler.process_alt_input_entry(mock_message, mock_state)
                assert mock_finish.called

@pytest.mark.asyncio
async def test_finish_alt_input_success(sync_test_session, mock_message, mock_state):
    """Test finish_alt_input successfully adding an alt."""
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()
    
    # Needs a main character to add alt
    main_char = Character(user_id=user.id, nickname="MainChar", is_main=True)
    sync_test_session.add(main_char)
    sync_test_session.commit()

    mock_message.text = "AltChar"

    with patch("handlers.user.get_menu_text", return_value=("Menu Text", False)):
        await user_handler.finish_alt_input(mock_message, mock_state)

    char = sync_test_session.query(Character).filter_by(nickname="AltChar").first()
    assert char is not None
    assert char.user_id == user.id
    assert not char.is_main
    assert mock_message.answer.called
    assert "Твин добавлен" in mock_message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_finish_alt_input_no_main(sync_test_session, mock_message, mock_state):
    """Test finish_alt_input failing due to no main character."""
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()
    
    mock_message.text = "AltChar"
    await user_handler.finish_alt_input(mock_message, mock_state)
    assert mock_message.answer.called
    assert "Сначала добавь" in mock_message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_afk_set_start(mock_callback_query, mock_state):
    """Test afk_set_start starts AFK date entry FSM."""
    await user_handler.afk_set_start(mock_callback_query, mock_state)
    assert mock_state.set_state.called
    assert mock_callback_query.message.edit_text.called

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
    from datetime import datetime
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
    
    from datetime import datetime
    mock_state.get_data = AsyncMock(return_value={"start_date": datetime(2026, 3, 1)})
    
    await user_handler.afk_end_quick(mock_callback_query, mock_state)
    assert mock_callback_query.message.edit_text.called
    assert mock_state.update_data.called

@pytest.mark.asyncio
async def test_afk_end_manual(mock_message, mock_state):
    """Test afk_end_manual with specific date text."""
    from datetime import datetime
    mock_state.get_data = AsyncMock(return_value={"start_date": datetime(2026, 3, 1)})
    mock_message.text = "15/03"
    with patch("handlers.user.parse_date_input", return_value=datetime(2026, 3, 15)):
        await user_handler.afk_end_manual(mock_message, mock_state)
        assert mock_message.answer.called
        assert mock_state.update_data.called

@pytest.mark.asyncio
async def test_finish_afk_setup(sync_test_session, mock_message, mock_state):
    """Test finish_afk_setup saves to DB and logs history."""
    from datetime import datetime
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()

    start = datetime(2026, 3, 12)
    end = datetime(2026, 3, 15)

    with patch("handlers.user.get_afk_menu", return_value=None):
        await user_handler.finish_afk_setup(mock_message, mock_state, start, end, None)
        
        updated_user = sync_test_session.get(User, user.id)
        assert updated_user.afk_start is not None
        assert updated_user.afk_end is not None
        assert mock_state.clear.called
        assert mock_message.answer.called

@pytest.mark.asyncio
async def test_send_approval_request(sync_test_session, mock_message, mock_state):
    """Test send_approval_request sends to master."""
    user = User(telegram_id=123456789, username="test_user")
    master = User(telegram_id=987654321, username="master", is_master=True)
    sync_test_session.add_all([user, master])
    sync_test_session.commit()

    with patch("handlers.user.get_menu_text", return_value=("Text", False)):
        await user_handler.send_approval_request(mock_message, mock_state, "NewNick", "main_input")

    assert mock_message.bot.send_message.called
    assert "Заявка на добавление" in mock_message.bot.send_message.call_args[0][1]

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
async def test_cmd_start_banned(sync_test_session, mock_message):
    user = User(telegram_id=123456789, username="test_user", is_banned=True)
    sync_test_session.add(user)
    sync_test_session.commit()
    await user_handler.cmd_start(mock_message)
    assert mock_message.answer.called
    assert "забанены" in mock_message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_start_pending_request(sync_test_session, mock_message):
    user = User(telegram_id=123456789, username="test_user", pending_request_nick="WaitChar")
    sync_test_session.add(user)
    sync_test_session.commit()
    await user_handler.cmd_start(mock_message)
    assert mock_message.answer.called
    assert "Заявка отправлена" in mock_message.answer.call_args[0][0]

@pytest.mark.asyncio
async def test_cmd_start_heals_main(sync_test_session, mock_message):
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()
    
    char = Character(user_id=user.id, nickname="AltChar", is_main=False)
    sync_test_session.add(char)
    sync_test_session.commit()
    
    with patch("handlers.user.get_menu_text", return_value=("Text", False)):
        await user_handler.cmd_start(mock_message)
        
    updated_char = sync_test_session.get(Character, char.id)
    assert updated_char.is_main is True
    assert mock_message.answer.called

@pytest.mark.asyncio
async def test_cancel_pending_request_no_nick(sync_test_session, mock_callback_query, mock_state):
    user = User(telegram_id=123456789, username="test_user", pending_request_nick=None)
    sync_test_session.add(user)
    sync_test_session.commit()
    
    with patch("handlers.user.cmd_start", new=AsyncMock()) as mock_start:
        await user_handler.cancel_pending_request(mock_callback_query, mock_state)
        
    assert mock_callback_query.answer.called
    assert mock_start.called

@pytest.mark.asyncio
async def test_main_menu_text(mock_message):
    with patch("handlers.user.cmd_start", new=AsyncMock()) as mock_start:
        await user_handler.main_menu_text(mock_message)
        assert mock_start.called

@pytest.mark.asyncio
async def test_confirm_del_char_complex_swap(sync_test_session, mock_callback_query):
    # Setup user and chars
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()
    
    main_char = Character(user_id=user.id, nickname="MainChar", is_main=True)
    alt_char = Character(user_id=user.id, nickname="AltChar", is_main=False)
    sync_test_session.add_all([main_char, alt_char])
    sync_test_session.commit()
    
    # Setup queue and entry
    from database import QueueType, QueueEntry
    queue = QueueType(name="TestQ", is_active=True)
    sync_test_session.add(queue)
    sync_test_session.commit()
    
    entry = QueueEntry(queue_type_id=queue.id, user_id=user.id, character_name="AltChar")
    sync_test_session.add(entry)
    sync_test_session.commit()
    
    mock_callback_query.data = f"conf_del_{alt_char.id}_swap"
    
    with patch("handlers.user.log_reward_to_sheet", new=AsyncMock()):
        await user_handler.confirm_del_char_complex(mock_callback_query)
        
    # Verify alt deleted, entry updated
    assert sync_test_session.get(Character, alt_char.id) is None
    entry_db = sync_test_session.get(QueueEntry, entry.id)
    assert entry_db.character_name == "MainChar"
    assert mock_callback_query.message.edit_text.called

@pytest.mark.asyncio
async def test_confirm_del_char_complex_kill(sync_test_session, mock_callback_query):
    user = User(telegram_id=123456789, username="test_user")
    sync_test_session.add(user)
    sync_test_session.commit()
    
    alt_char = Character(user_id=user.id, nickname="AltChar", is_main=False)
    sync_test_session.add(alt_char)
    sync_test_session.commit()
    
    from database import QueueType, QueueEntry
    queue = QueueType(name="TestQ", is_active=True)
    sync_test_session.add(queue)
    sync_test_session.commit()
    
    entry = QueueEntry(queue_type_id=queue.id, user_id=user.id, character_name="AltChar")
    sync_test_session.add(entry)
    sync_test_session.commit()
    
    mock_callback_query.data = f"conf_del_{alt_char.id}_kill"
    
    with patch("handlers.user.log_reward_to_sheet", new=AsyncMock()):
        await user_handler.confirm_del_char_complex(mock_callback_query)
        
    assert sync_test_session.get(Character, alt_char.id) is None
    assert sync_test_session.get(QueueEntry, entry.id) is None

@pytest.mark.asyncio
async def test_process_alt_input_entry_is_unknown_with_code(sync_test_session, mock_message, mock_state):
    """Test process_alt_input_entry when nick is unknown and code is required."""
    mock_message.text = "AltUnknown"
    
    with patch("handlers.user.check_google_sheet", new=AsyncMock(return_value=False)):
        with patch("handlers.user.get_setting", return_value="1234"):
            await user_handler.process_alt_input_entry(mock_message, mock_state)
            
            assert mock_message.answer.called
            assert "Возможно," in mock_message.answer.call_args[0][0]
            assert mock_state.set_state.called

def test_parse_date_input():
    from handlers.user import parse_date_input
    
    # Test DD.MM
    dt1 = parse_date_input("16.03")
    assert dt1 is not None
    assert dt1.day == 16
    assert dt1.month == 3
    
    # Test DD.MM.YY
    dt2 = parse_date_input("15.01.25")
    assert dt2 is not None
    assert dt2.day == 15
    assert dt2.month == 1
    assert dt2.year == 2025
    
    # Test DD.MM.YYYY
    dt3 = parse_date_input("20.12.2024")
    assert dt3 is not None
    assert dt3.day == 20
    assert dt3.month == 12
    assert dt3.year == 2024
    
    # Test invalid cases
    assert parse_date_input("invalid.date") is None
    assert parse_date_input("99.99") is None

