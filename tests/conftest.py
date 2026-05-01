"""Shared pytest fixtures.

Each test session points DATA_DIR at a fresh tmp directory so the test DB
and any recorded JSONL files are isolated from a developer's working data.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Run all DB-touching tests against an isolated DATA_DIR.
_TMP_DATA = Path(tempfile.mkdtemp(prefix="aruco-test-"))
os.environ["DATA_DIR"] = str(_TMP_DATA)

# Allow `from backend...` imports when running pytest from any cwd.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    """Initialise the test DB once per session."""
    from backend.db import init_db
    init_db()
    yield
