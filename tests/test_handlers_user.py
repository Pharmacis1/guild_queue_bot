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
