from tests.conftest import add_member


def make_project(client, headers, name="Launch") -> int:
    response = client.post("/projects", json={"name": name, "description": "Q4 launch"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def make_task(client, headers, project_id, **fields) -> dict:
    body = {"title": "Task", **fields}
    response = client.post(f"/projects/{project_id}/tasks", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_project_crud(client, admin):
    project_id = make_project(client, admin)
    assert client.get(f"/projects/{project_id}", headers=admin).json()["name"] == "Launch"

    updated = client.patch(f"/projects/{project_id}", json={"name": "Launch v2"}, headers=admin).json()
    assert updated["name"] == "Launch v2"
    assert updated["description"] == "Q4 launch"  # untouched field stays the same

    assert [p["id"] for p in client.get("/projects", headers=admin).json()] == [project_id]
    assert client.delete(f"/projects/{project_id}", headers=admin).status_code == 204
    assert client.get(f"/projects/{project_id}", headers=admin).status_code == 404


def test_only_admin_can_delete_project(client, admin):
    project_id = make_project(client, admin)
    member = add_member(client, admin, "member@a.com")
    assert client.delete(f"/projects/{project_id}", headers=member).status_code == 403


def test_task_crud(client, admin):
    project_id = make_project(client, admin)
    task = make_task(client, admin, project_id, title="Write spec", due_date="2026-11-15")
    assert task["status"] == "todo"

    updated = client.patch(f"/tasks/{task['id']}", json={"status": "in_progress"}, headers=admin).json()
    assert updated["status"] == "in_progress"
    assert updated["due_date"] == "2026-11-15"

    tasks = client.get(f"/projects/{project_id}/tasks", headers=admin).json()
    assert [t["title"] for t in tasks] == ["Write spec"]

    assert client.delete(f"/tasks/{task['id']}", headers=admin).status_code == 204
    assert client.get(f"/projects/{project_id}/tasks", headers=admin).json() == []


def test_invalid_status_rejected(client, admin):
    project_id = make_project(client, admin)
    response = client.post(f"/projects/{project_id}/tasks", json={"title": "x", "status": "finished"}, headers=admin)
    assert response.status_code == 422


def test_blocked_endpoint_shows_what_blocks_each_task(client, admin):
    project_id = make_project(client, admin)
    auth = make_task(client, admin, project_id, title="Build auth service")
    payments = make_task(client, admin, project_id, title="Payments API", depends_on_id=auth["id"])
    make_task(client, admin, project_id, title="Landing page", status="blocked")
    make_task(client, admin, project_id, title="Logo")

    blocked = client.get("/tasks/blocked", headers=admin).json()
    by_title = {b["task"]["title"]: b for b in blocked}
    assert set(by_title) == {"Payments API", "Landing page"}
    assert by_title["Payments API"]["blocked_by"]["id"] == auth["id"]
    assert by_title["Landing page"]["blocked_by"] is None

    # Finish the dependency and the task is no longer blocked.
    client.patch(f"/tasks/{auth['id']}", json={"status": "done"}, headers=admin)
    titles = [b["task"]["title"] for b in client.get("/tasks/blocked", headers=admin).json()]
    assert payments["title"] not in titles


def test_dependency_cycle_rejected(client, admin):
    project_id = make_project(client, admin)
    a = make_task(client, admin, project_id, title="A")
    b = make_task(client, admin, project_id, title="B", depends_on_id=a["id"])
    response = client.patch(f"/tasks/{a['id']}", json={"depends_on_id": b["id"]}, headers=admin)
    assert response.status_code == 400
    assert "cycle" in response.json()["detail"]

    self_loop = client.patch(f"/tasks/{a['id']}", json={"depends_on_id": a["id"]}, headers=admin)
    assert self_loop.status_code == 400


def test_dependency_must_be_in_same_project(client, admin):
    first = make_project(client, admin, "One")
    second = make_project(client, admin, "Two")
    task = make_task(client, admin, first, title="A")
    response = client.post(f"/projects/{second}/tasks", json={"title": "B", "depends_on_id": task["id"]}, headers=admin)
    assert response.status_code == 400


def test_deleting_a_task_clears_dependents(client, admin):
    project_id = make_project(client, admin)
    a = make_task(client, admin, project_id, title="A")
    b = make_task(client, admin, project_id, title="B", depends_on_id=a["id"])
    client.delete(f"/tasks/{a['id']}", headers=admin)
    assert client.get(f"/tasks/{b['id']}", headers=admin).json()["depends_on_id"] is None
