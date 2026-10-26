import json

import pytest

from tests.conftest import add_member

BRIEF = "We launch the mobile app on 1 Dec. Need login, payments, and a landing page. Payments need login first."

GOOD_PLAN = json.dumps({
    "tasks": [
        {"title": "Build login", "description": "Email and password", "depends_on": None, "estimate_days": 3},
        {"title": "Integrate payments", "description": "", "depends_on": 1, "estimate_days": 5},
        {"title": "Design landing page", "description": "", "depends_on": None, "estimate_days": None},
    ]
})
BAD_PLAN = json.dumps({"tasks": [{"title": "Integrate payments", "depends_on": 2}]})  # points forward


@pytest.fixture()
def project_id(client, admin):
    return client.post("/projects", json={"name": "Mobile launch"}, headers=admin).json()["id"]


def create_plan(client, headers, project_id):
    return client.post("/planner/plans", json={"project_id": project_id, "brief": BRIEF}, headers=headers)


def test_plan_is_saved_as_pending_and_creates_no_tasks(client, admin, project_id, fake_llm):
    fake_llm.queue(GOOD_PLAN)
    response = create_plan(client, admin, project_id)
    assert response.status_code == 201
    plan = response.json()
    assert plan["status"] == "pending"
    assert len(plan["plan_json"]["tasks"]) == 3
    assert client.get(f"/projects/{project_id}/tasks", headers=admin).json() == []


def test_invalid_reply_is_retried_once_with_the_error(client, admin, project_id, fake_llm):
    fake_llm.queue("Sure! Here is your plan: " + BAD_PLAN, GOOD_PLAN)
    response = create_plan(client, admin, project_id)
    assert response.status_code == 201
    assert len(fake_llm.calls) == 2
    _, retry_prompt = fake_llm.calls[1]
    assert "rejected by the validator" in retry_prompt


def test_two_invalid_replies_fail_and_are_logged(client, admin, project_id, fake_llm):
    fake_llm.queue("not json at all", BAD_PLAN)
    response = create_plan(client, admin, project_id)
    assert response.status_code == 502
    assert client.get("/planner/plans", headers=admin).json() == []
    rows = client.get("/audit", headers=admin).json()
    assert rows[0]["action"] == "plan_generate"
    assert rows[0]["status"] == "failed"


def test_member_can_suggest_but_not_approve(client, admin, project_id, fake_llm):
    member = add_member(client, admin, "member@a.com")
    fake_llm.queue(GOOD_PLAN)
    plan = create_plan(client, member, project_id).json()
    assert client.post(f"/planner/plans/{plan['id']}/approve", headers=member).status_code == 403
    assert client.post(f"/planner/plans/{plan['id']}/reject", headers=member).status_code == 403


def test_admin_approval_creates_tasks_with_dependencies(client, admin, project_id, fake_llm):
    fake_llm.queue(GOOD_PLAN)
    plan = create_plan(client, admin, project_id).json()

    response = client.post(f"/planner/plans/{plan['id']}/approve", headers=admin)
    assert response.status_code == 200
    login_task, payments_task, landing_task = response.json()
    assert payments_task["depends_on_id"] == login_task["id"]
    assert landing_task["depends_on_id"] is None
    assert "Estimate: 3 day(s)" in login_task["description"]

    assert client.get(f"/planner/plans/{plan['id']}", headers=admin).json()["status"] == "approved"
    # Approving twice must not create the tasks twice.
    assert client.post(f"/planner/plans/{plan['id']}/approve", headers=admin).status_code == 400
    assert len(client.get(f"/projects/{project_id}/tasks", headers=admin).json()) == 3


def test_reject_keeps_tasks_untouched_and_is_audited(client, admin, project_id, fake_llm):
    fake_llm.queue(GOOD_PLAN)
    plan = create_plan(client, admin, project_id).json()
    assert client.post(f"/planner/plans/{plan['id']}/reject", headers=admin).json()["status"] == "rejected"
    assert client.get(f"/projects/{project_id}/tasks", headers=admin).json() == []

    rows = client.get("/audit", headers=admin).json()
    assert [(r["action"], r["status"]) for r in rows] == [("plan_review", "rejected"), ("plan_generate", "rejected")]


def test_brief_is_wrapped_as_data(client, admin, project_id, fake_llm):
    fake_llm.queue(GOOD_PLAN)
    create_plan(client, admin, project_id)
    system, user_prompt = fake_llm.calls[0]
    assert "ignore them" in system
    assert user_prompt.startswith("<brief>")


def test_deleting_project_keeps_audit_history(client, admin, project_id, fake_llm):
    fake_llm.queue(GOOD_PLAN)
    create_plan(client, admin, project_id)
    assert client.delete(f"/projects/{project_id}", headers=admin).status_code == 204
    rows = client.get("/audit", headers=admin).json()
    assert len(rows) == 1
    assert rows[0]["plan_id"] is None
