import asyncio
import os
import sys

import pytest

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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
    Initialize a test database, create schema, and override the global string variables.
    Returns: The temporary DB path.
    """
    # Override configured DB paths
    monkeypatch.setattr("web_database.DB_NAME", test_db_path)
    # Note: database.py uses hardcoded string in create_engine, so we need to patch the engine creation or Base.metadata.create_all
    # But since database.py initializes engine at module level, standard monkeypatching the variable might be too late if it's already imported.
    # However, for tests importing 'database', we can try to re-bind or patch the session/engine if possible.
    
    # 1. Create Schema using SQLAlchemy
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database import Base
    
    engine = create_engine(f'sqlite:///{test_db_path}')
    Base.metadata.create_all(engine)
    
    # 2. Monkeypatch 'database.engine' and 'database.session'? 
    # This is tricky because `database.py` creates `session = Session()` at module level.
    # Any code doing `from database import session` already has the old object.
    
    # Better approach for integration tests code that imports `database`:
    # We should probably refactor `database.py` to allow overriding, but for now let's try to patch.
    
    # Init new session factory for test DB
    TestSession = sessionmaker(bind=engine)
    test_session = TestSession()
    
    # Patch the module-level 'session' object if possible, BUT 'from database import session' creates a reference we can't easily update universally
    # unless we patch where it is used.
    # HOWEVER, web_database uses `aiosqlite.connect(DB_NAME)`, which we patched via monkeypatch.
    # So `web_database` logic is SAFE.
    
    # The `database.py` synchronous partial logic (for bot handlers) uses `session`.
    # Let's verify if `test_database.py` tests `web_database` (async) or `database` (sync).
    # It tests `web_database`. So patching `DB_NAME` is enough for `web_database`.
    
    yield test_db_path
    
    # Cleanup
    test_session.close()
    # tmp_path is auto-cleaned

