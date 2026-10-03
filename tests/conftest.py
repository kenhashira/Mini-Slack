import pytest
from fastapi.testclient import TestClient

from app.db import connect
from app.main import create_app


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def client(db_path):
    return TestClient(create_app(db_path))


@pytest.fixture
def conn(client, db_path):
    """Direct connection to the same test database (depends on client so the schema exists)."""
    c = connect(db_path)
    yield c
    c.close()
