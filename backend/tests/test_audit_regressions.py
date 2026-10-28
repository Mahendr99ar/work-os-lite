"""Regression tests for bugs found in the October 2026 audit.

Each test was written first, run against the old code to confirm the bug,
and then kept to make sure the bug does not come back.
"""

import json
import threading
import time

import httpx
import pytest

from app.config import settings
from app.database import SessionLocal, is_postgres
from app.models import AuditLog, Task
from app.services import llm
from tests.conftest import add_member, signup

PLAN = json.dumps({"tasks": [
    {"title": "Build login", "description": "", "depends_on": None, "estimate_days": 2},
    {"title": "Integrate payments", "description": "", "depends_on": 1, "estimate_days": 3},
]})
BRIEF = "Launch on 1 Dec with login and payments. Payments need login first."


def make_plan(client, headers, fake_llm) -> tuple[int, int]:
    project_id = client.post("/projects", json={"name": "Launch"}, headers=headers).json()["id"]
    fake_llm.queue(PLAN)
    plan_id = client.post("/planner/plans", json={"project_id": project_id, "brief": BRIEF}, headers=headers).json()["id"]
    return project_id, plan_id


# ---------- AI planner approval ----------

@pytest.mark.skipif(not is_postgres(), reason="needs real row locking; SQLite serialises every write anyway")
def test_concurrent_approvals_create_tasks_once(client, admin, fake_llm, monkeypatch):
    """Two admins (or a double click) approving the same plan at the same moment."""
    project_id, plan_id = make_plan(client, admin, fake_llm)

    # Slow down the approval so both requests are inside it at the same time.
    from app.routers import planner as planner_router
    original = planner_router.TaskPlan.model_validate
    barrier = threading.Barrier(2, timeout=5)

    def slow_validate(data, *args, **kwargs):
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass  # the fixed code lets only one request get this far
        time.sleep(0.3)
        return original(data, *args, **kwargs)

    monkeypatch.setattr(planner_router.TaskPlan, "model_validate", slow_validate)

    codes: list[int] = []

    def approve():
        codes.append(client.post(f"/planner/plans/{plan_id}/approve", headers=admin).status_code)

    threads = [threading.Thread(target=approve) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    tasks = client.get(f"/projects/{project_id}/tasks", headers=admin).json()
    assert sorted(codes) == [200, 409]
    assert len(tasks) == 2  # not 4


def test_plan_status_and_tasks_stay_consistent_after_reload(client, admin, fake_llm):
    """What the planner page, the overview and the database show after approving and reloading."""
    project_id, plan_id = make_plan(client, admin, fake_llm)
    client.post(f"/planner/plans/{plan_id}/approve", headers=admin)

    # A reload re-fetches everything from the API.
    plans = client.get("/planner/plans", headers=admin).json()
    assert [(p["id"], p["status"]) for p in plans] == [(plan_id, "approved")]
    assert [p for p in plans if p["status"] == "pending"] == []  # overview's "waiting for review" list
    tasks = client.get("/tasks", headers=admin).json()
    assert [(t["title"], t["status"]) for t in tasks] == [("Build login", "todo"), ("Integrate payments", "todo")]

    with SessionLocal() as db:
        assert db.query(Task).filter(Task.project_id == project_id).count() == 2

    # Approving or rejecting again is refused with a conflict, and nothing changes.
    assert client.post(f"/planner/plans/{plan_id}/approve", headers=admin).status_code == 409
    assert client.post(f"/planner/plans/{plan_id}/reject", headers=admin).status_code == 409
    assert len(client.get("/tasks", headers=admin).json()) == 2


def test_review_does_not_rewrite_earlier_audit_rows(client, admin, fake_llm):
    """An audit log is append-only: approving must add a row, not edit the generation row."""
    _, plan_id = make_plan(client, admin, fake_llm)
    with SessionLocal() as db:
        before = {(r.id, r.action, r.status) for r in db.query(AuditLog).all()}

    client.post(f"/planner/plans/{plan_id}/approve", headers=admin)

    with SessionLocal() as db:
        after = {(r.id, r.action, r.status) for r in db.query(AuditLog).all()}
    assert before <= after  # every earlier row is unchanged
    assert {(a, s) for _, a, s in after - before} == {("plan_review", "approved")}


# ---------- rate limiting ----------

def test_forged_forwarded_for_header_does_not_bypass_login_limit(client):
    signup(client, "Team A", "admin@a.com")
    codes = []
    for i in range(12):
        # An attacker sends a different fake address each time. The proxy appends the real one last.
        headers = {"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.7"}
        codes.append(client.post("/auth/login", data={"username": "admin@a.com", "password": "wrong-pass"},
                                 headers=headers).status_code)
    assert codes[-1] == 429


# ---------- secrets ----------

def test_default_jwt_secret_is_refused_on_postgres(monkeypatch):
    from dataclasses import replace

    from app import main

    monkeypatch.setattr(main, "settings", replace(settings, jwt_secret="change-me-in-production",
                                                  database_url="postgresql://u:p@db.example/x"))
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        main.check_settings()


# ---------- LLM reliability ----------

class FakeResponse:
    def __init__(self, status_code: int, payload: dict, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)
        self.headers = headers or {}

    def json(self):
        return self._payload


def _openai_settings(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(llm, "settings", replace(settings, llm_provider="groq", llm_api_key="k",
                                                 llm_base_url="https://api.groq.com/openai/v1", llm_model="m"))
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)  # no real waiting in tests


def test_llm_retries_temporary_failures_then_succeeds(monkeypatch):
    _openai_settings(monkeypatch)
    replies = [FakeResponse(503, {"error": "overloaded"}), FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]})]
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs.get("timeout"))
        return replies.pop(0)

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm.complete("s", "u") == "ok"
    assert len(calls) == 2


def test_llm_retries_timeouts_a_limited_number_of_times(monkeypatch):
    _openai_settings(monkeypatch)
    calls = []

    def always_timeout(*args, **kwargs):
        calls.append(1)
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(llm.httpx, "post", always_timeout)
    with pytest.raises(llm.LLMError, match="did not answer"):
        llm.complete("s", "u")
    assert len(calls) == llm.MAX_ATTEMPTS


def test_llm_does_not_retry_a_bad_key(monkeypatch):
    _openai_settings(monkeypatch)
    calls = []

    def unauthorized(*args, **kwargs):
        calls.append(1)
        return FakeResponse(401, {"error": "invalid key"})

    monkeypatch.setattr(llm.httpx, "post", unauthorized)
    with pytest.raises(llm.LLMError, match="rejected the API key"):
        llm.complete("s", "u")
    assert len(calls) == 1


def test_provider_error_body_is_not_shown_to_users(client, admin, monkeypatch):
    _openai_settings(monkeypatch)
    monkeypatch.setattr(llm.httpx, "post",
                        lambda *a, **k: FakeResponse(500, {"error": "internal trace id abc123 at host gpu-77"}))
    client.post("/documents", files={"file": ("leave.txt", b"Leave policy: 18 days of paid leave.", "text/plain")},
                headers=admin)
    response = client.post("/ask", json={"question": "How many days of paid leave?"}, headers=admin)
    assert response.status_code == 502
    assert "gpu-77" not in response.text


# ---------- uploads and input ----------

def test_oversized_upload_is_rejected_without_storing_anything(client, admin):
    big = b"a " * (3 * 1024 * 1024)  # 6 MB
    response = client.post("/documents", files={"file": ("big.txt", big, "text/plain")}, headers=admin)
    assert response.status_code == 413
    assert client.get("/documents", headers=admin).json() == []


def test_member_cannot_read_audit_log(client, admin):
    member = add_member(client, admin, "m@a.com")
    assert client.get("/audit", headers=member).status_code == 403
