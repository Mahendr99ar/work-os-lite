"""Hosting-related behaviour: demo sandboxes, health, limits, LLM providers, error handling."""

import httpx
import pytest

from app.config import settings
from app.services import llm, rag
from tests.conftest import signup


def demo_headers(client) -> dict:
    response = client.post("/auth/demo")
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_health_checks_database(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}


def test_ping_does_not_touch_the_database(client, monkeypatch):
    from app import main

    def no_db(*args, **kwargs):
        raise AssertionError("/ping must not open a database connection")

    monkeypatch.setattr(main.engine, "connect", no_db)
    assert client.get("/ping").json() == {"status": "ok"}


def test_meta_exposes_no_secrets(client):
    body = client.get("/meta").json()
    assert body["llm_configured"] is True
    assert body["demo_mode"] is True
    assert "test-key" not in str(body)


def test_demo_workspace_is_ready_to_use(client):
    headers = demo_headers(client)
    me = client.get("/auth/me", headers=headers).json()
    assert me["role"] == "admin"
    assert me["team_name"] == "Acme Mobile (demo)"

    assert len(client.get("/projects", headers=headers).json()) == 2
    assert len(client.get("/tasks", headers=headers).json()) == 8
    assert len(client.get("/documents", headers=headers).json()) == 3
    assert len(client.get("/team/members", headers=headers).json()) == 3
    blocked = client.get("/tasks/blocked", headers=headers).json()
    assert {b["task"]["title"] for b in blocked} == {"Payments API", "Order tracking screen", "App store listing"}

    plans = client.get("/planner/plans", headers=headers).json()
    assert [p["status"] for p in plans] == ["pending"]
    created = client.post(f"/planner/plans/{plans[0]['id']}/approve", headers=headers).json()
    assert len(created) == 4
    assert created[2]["depends_on_id"] == created[1]["id"]


def test_each_demo_visitor_gets_a_separate_team(client):
    first, second = demo_headers(client), demo_headers(client)
    project = client.get("/projects", headers=first).json()[0]
    client.patch(f"/projects/{project['id']}", json={"name": "Changed by visitor one"}, headers=first)
    assert client.get(f"/projects/{project['id']}", headers=second).status_code == 404
    names = [p["name"] for p in client.get("/projects", headers=second).json()]
    assert "Changed by visitor one" not in names


def test_demo_can_be_turned_off(client, monkeypatch):
    # Settings is frozen, so swap the module-level object for a copy with demo off.
    from dataclasses import replace

    from app.routers import auth
    monkeypatch.setattr(auth, "settings", replace(settings, demo_mode=False))
    assert client.post("/auth/demo").status_code == 404


def test_login_is_rate_limited(client):
    signup(client, "Team A", "admin@a.com")
    codes = [client.post("/auth/login", data={"username": "admin@a.com", "password": "wrong-pass"}).status_code
             for _ in range(12)]
    assert codes[:9] == [401] * 9  # signup used one slot of the 10
    assert codes[-1] == 429


def test_ask_is_rate_limited_per_user(client, admin, fake_llm):
    codes = [client.post("/ask", json={"question": "anything at all?"}, headers=admin).status_code for _ in range(21)]
    assert codes[-1] == 429
    assert set(codes[:20]) == {200}


def test_missing_api_key_gives_a_clear_message(client, admin, monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(llm, "settings", replace(settings, llm_api_key=""))
    client.post("/documents", files={"file": ("leave.txt", b"Leave policy: 18 days of paid leave per year.", "text/plain")},
                headers=admin)
    response = client.post("/ask", json={"question": "How many days of paid leave?"}, headers=admin)
    assert response.status_code == 503
    assert "LLM_API_KEY" in response.json()["detail"]


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)
        self.headers: dict = {}

    def json(self):
        return self._payload


@pytest.mark.parametrize("provider,url", [
    ("groq", "https://api.groq.com/openai/v1/chat/completions"),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"),
    ("openai", "https://api.openai.com/v1/chat/completions"),
])
def test_openai_compatible_providers_send_the_right_request(monkeypatch, provider, url):
    from dataclasses import replace

    from app.config import PROVIDERS

    base, model = PROVIDERS[provider]
    monkeypatch.setattr(llm, "settings", replace(settings, llm_provider=provider, llm_base_url=base,
                                                 llm_model=model, llm_api_key="k-123"))
    sent = {}

    def fake_post(target, headers, json, timeout):
        sent.update(url=target, headers=headers, body=json)
        return FakeResponse(200, {"choices": [{"message": {"content": "hello"}}]})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm.complete("sys", "user") == "hello"
    assert sent["url"] == url
    assert sent["headers"]["Authorization"] == "Bearer k-123"
    assert sent["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert sent["body"]["model"] == model


def test_anthropic_request_shape(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(llm, "settings", replace(settings, llm_provider="anthropic", llm_api_key="sk-ant",
                                                 llm_base_url="https://api.anthropic.com/v1", llm_model="claude-x"))
    sent = {}

    def fake_post(target, headers, json, timeout):
        sent.update(url=target, headers=headers, body=json)
        return FakeResponse(200, {"content": [{"type": "text", "text": "hi"}]})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm.complete("sys", "user") == "hi"
    assert sent["url"] == "https://api.anthropic.com/v1/messages"
    assert sent["headers"]["x-api-key"] == "sk-ant"
    assert sent["body"]["system"] == "sys"


def test_provider_errors_become_llm_errors(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)  # skip the retry wait

    def rate_limited(*args, **kwargs):
        return FakeResponse(429, {"error": "slow down"})

    monkeypatch.setattr(llm.httpx, "post", rate_limited)
    with pytest.raises(llm.LLMError, match="rate limit"):
        llm.complete("s", "u")

    def offline(*args, **kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(llm.httpx, "post", offline)
    with pytest.raises(llm.LLMError, match="Could not reach"):
        llm.complete("s", "u")


def test_crash_returns_json_with_cors_headers(client, admin, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(rag, "answer", broken)
    response = client.post("/ask", json={"question": "anything?"},
                           headers={**admin, "Origin": "http://localhost:5173"})
    assert response.status_code == 500
    assert response.json()["detail"].startswith("Something went wrong")
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_list_all_tasks_is_team_scoped(client):
    a = signup(client, "Team A", "admin@a.com")
    b = signup(client, "Team B", "admin@b.com")
    project = client.post("/projects", json={"name": "P"}, headers=a).json()
    client.post(f"/projects/{project['id']}/tasks", json={"title": "Only A"}, headers=a)
    assert [t["title"] for t in client.get("/tasks", headers=a).json()] == ["Only A"]
    assert client.get("/tasks", headers=b).json() == []
