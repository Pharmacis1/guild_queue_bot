import asyncio
import os
import sys

# Force SQLite for tests to avoid asyncpg dependency if not installed
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import pytest

import sys
from unittest.mock import MagicMock

# --- Mock google.genai globally for pytest collection ---
try:
    import google.genai
except ImportError:
    # If the environment is fundamentally broken for pytest namespace packages,
    # mock it out entirely to allow test collection of all other modules.
    sys.modules['google.genai'] = MagicMock()
    sys.modules['google.genai.types'] = MagicMock()

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_db_path(tmp_path):
    """Create a temporary database file."""
    d = tmp_path / "test_guild_bot.db"
    return str(d)


@pytest.fixture
def test_db_session(test_db_path, monkeypatch):
    """
    Initialize a test database, create schema.
    Returns: The temporary DB path (for legacy sync tests).
    """
    # [IMPORTANT] Ensure all models are registered with Base.metadata
    from database import Base
    import database # ensures all models in database.py are loaded
    
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{test_db_path}")
    Base.metadata.create_all(engine)
    engine.dispose()

    monkeypatch.setattr("web_database.DB_NAME", test_db_path)
    
    # [IMPORTANT] Ensure any code using AsyncSessionLocal uses the test database
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    import database
    async_engine = create_async_engine(f"sqlite+aiosqlite:///{test_db_path}")
    test_async_session_factory = async_sessionmaker(bind=async_engine, expire_on_commit=False)
    
    # Monkeypatch the factories in modules that use them
    for module_name in [
        "database", "web_database", "logic.dashboard", "logic.party_manager", 
        "logic.player_manager", "logic.queue_ops", "logic.queue_manager", 
        "logic.reward_ops", "logic.ai_helper", "logic.log_importer", "handlers.user", "handlers.ai_user",
        "routers.api", "routers.api_dashboard", "routers.admin_browser", "routers.auth", "routers.observer", "routers.views"
    ]:
        try:
            import importlib
            mod = importlib.import_module(module_name)
            if hasattr(mod, "AsyncSessionLocal"):
                monkeypatch.setattr(f"{module_name}.AsyncSessionLocal", test_async_session_factory)
        except ImportError:
            pass

    # We yield the path because legacy tests do: create_engine(f"sqlite:///{test_db_session}")
    yield test_db_path


@pytest.fixture(autouse=True)
def patch_async_session(monkeypatch, tmp_path_factory):
    """
    Globally patch AsyncSessionLocal for ALL tests to use an in-memory or temp SQLite DB.
    This prevents accidental PostgreSQL connections.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from database import Base
    import database
    
    # Create a session-wide temp DB path if not already created
    # For simplicity, we can use a unique path per test if needed, 
    # but autouse=True at function level is safer for isolation.
    test_db = tmp_path_factory.mktemp("data") / "test.db"
    
    # Create tables synchronously first
    from sqlalchemy import create_engine
    sync_engine = create_engine(f"sqlite:///{test_db}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    
    engine = create_async_engine(f"sqlite+aiosqlite:///{test_db}")
    AsyncTestSession = async_sessionmaker(bind=engine, expire_on_commit=False)
    
    modules_to_patch = [
        "database", "web_database", "logic.dashboard", "logic.player_manager", 
        "logic.party_manager", "logic.queue_ops", "logic.queue_manager", 
        "logic.reward_ops", "logic.ai_helper", "logic.log_importer", "handlers.user", "handlers.ai_user",
        "handlers.admin", "handlers.ai_admin",
        "routers.api", "routers.api_dashboard", "routers.admin_browser", "routers.auth", "routers.observer", "routers.views"
    ]
    
    for module_name in modules_to_patch:
        try:
            import importlib
            mod = importlib.import_module(module_name)
            if hasattr(mod, "AsyncSessionLocal"):
                monkeypatch.setattr(f"{module_name}.AsyncSessionLocal", AsyncTestSession)
        except (ImportError, AttributeError):
            pass
            
    # Also patch the global engine in database.py
    monkeypatch.setattr("database.engine", engine)
    
    return AsyncTestSession

@pytest.fixture
async def async_test_session(patch_async_session, test_db_path):
    """
    Provides a clean session for async tests.
    """
    from database import Base
    AsyncTestSession = patch_async_session
    engine = AsyncTestSession.kw['bind']

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncTestSession() as session:
        yield session
    
    # Engine is shared by autouse fixture, so don't dispose here if you want it to persist 
    # for the duration of the function. Actually, since patch_async_session is function-scoped,
    # disposing is fine here if it was the last thing. 
    # But usually engine disposal is handled by the fixture that created it.
