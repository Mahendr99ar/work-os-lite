"""Shared test setup.

Settings are read when the app is imported, so the environment is set first.
By default tests use a throwaway SQLite file. Set TEST_DATABASE_URL to run the
same tests on Postgres + pgvector (CI does this).
"""

import os
import tempfile

_db_file = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", f"sqlite:///{_db_file}")
os.environ["JWT_SECRET"] = "work-os-lite-test-secret-at-least-32-bytes"
os.environ["EMBEDDING_PROVIDER"] = "hash"
os.environ["LLM_PROVIDER"] = "groq"
os.environ["LLM_API_KEY"] = "test-key"  # never sent anywhere: tests replace the LLM with the fake below
os.environ["DEMO_MODE"] = "true"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.ratelimit import ALL_LIMITERS  # noqa: E402
from app.services import llm  # noqa: E402


@pytest.fixture()
def client():
    for limiter in ALL_LIMITERS:
        limiter.reset()
    init_db()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


class FakeLLM:
    """Stands in for the real model. Returns queued replies in order and records every call."""

    def __init__(self):
        self.replies: list[str] = []
        self.calls: list[tuple[str, str]] = []

    def queue(self, *replies: str) -> None:
        self.replies.extend(replies)

    def __call__(self, system: str, user: str, max_tokens: int = 1500) -> str:
        self.calls.append((system, user))
        if not self.replies:
            raise AssertionError("FakeLLM was called but no reply was queued")
        return self.replies.pop(0)


@pytest.fixture()
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm, "complete", fake)
    return fake


def signup(client: TestClient, team: str, email: str, password: str = "password123") -> dict:
    response = client.post("/auth/signup", json={"team_name": team, "email": email, "password": password})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def login(client: TestClient, email: str, password: str = "password123") -> dict:
    response = client.post("/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def add_member(client: TestClient, admin: dict, email: str, role: str = "member") -> dict:
    response = client.post("/team/members", json={"email": email, "password": "password123", "role": role}, headers=admin)
    assert response.status_code == 201, response.text
    return login(client, email)


@pytest.fixture()
def admin(client):
    return signup(client, "Team A", "admin@a.com")
