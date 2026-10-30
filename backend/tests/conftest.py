import os
import tempfile
from pathlib import Path
import pytest

_test_root = Path(tempfile.mkdtemp(prefix="bn-inven-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_test_root / 'test.db'}"
os.environ["STORAGE_PATH"] = str(_test_root / "uploads")
os.environ["AI_PROVIDER"] = "mock"


@pytest.fixture(scope="session", autouse=True)
def apply_test_migrations():
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")
