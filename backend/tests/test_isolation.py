"""Team A must never see or change Team B's data. These are the most important tests in the repo."""

import pytest

from tests.conftest import signup


@pytest.fixture()
def two_teams(client):
    team_a = signup(client, "Team A", "admin@a.com")
    team_b = signup(client, "Team B", "admin@b.com")
    project = client.post("/projects", json={"name": "Secret A project"}, headers=team_a).json()
    task = client.post(f"/projects/{project['id']}/tasks", json={"title": "Secret task"}, headers=team_a).json()
    files = {"file": ("salaries.txt", b"Team A salary bands are confidential and reviewed every March.", "text/plain")}
    document = client.post("/documents", files=files, headers=team_a).json()
    return team_a, team_b, project, task, document


def test_other_team_gets_404_on_project(client, two_teams):
    _, team_b, project, _, _ = two_teams
    assert client.get(f"/projects/{project['id']}", headers=team_b).status_code == 404
    assert client.patch(f"/projects/{project['id']}", json={"name": "hacked"}, headers=team_b).status_code == 404
    assert client.delete(f"/projects/{project['id']}", headers=team_b).status_code == 404
    assert client.get(f"/projects/{project['id']}/tasks", headers=team_b).status_code == 404


def test_other_team_gets_404_on_task(client, two_teams):
    _, team_b, _, task, _ = two_teams
    assert client.get(f"/tasks/{task['id']}", headers=team_b).status_code == 404
    assert client.patch(f"/tasks/{task['id']}", json={"status": "done"}, headers=team_b).status_code == 404
    assert client.delete(f"/tasks/{task['id']}", headers=team_b).status_code == 404


def test_lists_only_show_own_team(client, two_teams):
    team_a, team_b, _, _, _ = two_teams
    assert client.get("/projects", headers=team_b).json() == []
    assert client.get("/documents", headers=team_b).json() == []
    assert client.get("/tasks/blocked", headers=team_b).json() == []
    assert [m["email"] for m in client.get("/team/members", headers=team_b).json()] == ["admin@b.com"]
    assert len(client.get("/projects", headers=team_a).json()) == 1


def test_cannot_link_to_other_team_rows(client, two_teams):
    team_a, team_b, _, task, _ = two_teams
    own_project = client.post("/projects", json={"name": "B project"}, headers=team_b).json()
    response = client.post(f"/projects/{own_project['id']}/tasks",
                           json={"title": "x", "depends_on_id": task["id"]}, headers=team_b)
    assert response.status_code == 400

    a_admin_id = client.get("/auth/me", headers=team_a).json()["id"]
    response = client.post(f"/projects/{own_project['id']}/tasks",
                           json={"title": "x", "assignee_id": a_admin_id}, headers=team_b)
    assert response.status_code == 400


def test_other_team_cannot_delete_document(client, two_teams):
    _, team_b, _, _, document = two_teams
    assert client.delete(f"/documents/{document['id']}", headers=team_b).status_code == 404


def test_rag_never_returns_other_team_documents(client, two_teams, fake_llm):
    _, team_b, _, _, _ = two_teams
    response = client.post("/ask", json={"question": "When are Team A salary bands reviewed?"}, headers=team_b)
    body = response.json()
    assert body["refused"] is True
    assert body["sources"] == []
    assert fake_llm.calls == []  # Team A's text never reached the model on Team B's behalf


def test_other_team_cannot_create_plan_for_my_project(client, two_teams, fake_llm):
    _, team_b, project, _, _ = two_teams
    response = client.post("/planner/plans", json={"project_id": project["id"], "brief": "x" * 30}, headers=team_b)
    assert response.status_code == 404
    assert fake_llm.calls == []
