"""Task CRUD, dependencies, and the "what is blocked" view."""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.deps import TeamScope, get_scope
from app.models import Project, Task, User
from app.schemas import BlockedTaskOut, TaskIn, TaskOut, TaskUpdate

router = APIRouter(tags=["tasks"])

STATUS_WORDS = {"todo": "not started", "in_progress": "in progress", "blocked": "blocked"}


def _check_links(scope: TeamScope, task: Task) -> None:
    """Validate assignee and dependency. Both must belong to the caller's team."""
    if task.assignee_id is not None and scope.find(User, task.assignee_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Assignee is not in your team")

    if task.depends_on_id is None:
        return
    parent = scope.find(Task, task.depends_on_id)
    if parent is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "depends_on task not found")
    if parent.project_id != task.project_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A task can only depend on a task in the same project")

    # Walk up the chain. If we come back to this task, the new link would make a loop.
    seen: set[int] = set()
    current: Task | None = parent
    while current is not None:
        if task.id is not None and current.id == task.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "This dependency would create a cycle")
        if current.id in seen:
            break
        seen.add(current.id)
        current = scope.find(Task, current.depends_on_id)


@router.post("/projects/{project_id}/tasks", response_model=TaskOut, status_code=201)
def create_task(project_id: int, body: TaskIn, scope: TeamScope = Depends(get_scope)) -> Task:
    scope.get(Project, project_id)
    task = Task(project_id=project_id, **body.model_dump())
    _check_links(scope, task)
    scope.add(task)
    scope.db.commit()
    return task


@router.get("/projects/{project_id}/tasks", response_model=list[TaskOut])
def list_tasks(project_id: int, scope: TeamScope = Depends(get_scope)) -> list[Task]:
    scope.get(Project, project_id)
    return list(scope.db.scalars(scope.select(Task).where(Task.project_id == project_id).order_by(Task.id)))


@router.get("/tasks", response_model=list[TaskOut])
def list_all_tasks(scope: TeamScope = Depends(get_scope)) -> list[Task]:
    """Every task in the team, across projects. The overview page uses this."""
    return list(scope.db.scalars(scope.select(Task).order_by(Task.id)))


@router.get("/tasks/blocked", response_model=list[BlockedTaskOut])
def blocked_tasks(scope: TeamScope = Depends(get_scope)) -> list[BlockedTaskOut]:
    """A task is blocked if someone marked it "blocked", or if the task it depends on is not done."""
    result = []
    for task in scope.db.scalars(scope.select(Task).where(Task.status != "done").order_by(Task.id)):
        parent = task.depends_on
        if parent is not None and parent.status != "done":
            reason = f'Waiting on "{parent.title}", which is {STATUS_WORDS.get(parent.status, parent.status)}'
        elif task.status == "blocked":
            reason = "Marked as blocked"
        else:
            continue
        result.append(
            BlockedTaskOut(
                task=TaskOut.model_validate(task),
                reason=reason,
                blocked_by=TaskOut.model_validate(parent) if parent is not None and parent.status != "done" else None,
            )
        )
    return result


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int, scope: TeamScope = Depends(get_scope)) -> Task:
    return scope.get(Task, task_id)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, body: TaskUpdate, scope: TeamScope = Depends(get_scope)) -> Task:
    task = scope.get(Task, task_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    _check_links(scope, task)
    scope.db.commit()
    return task


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, scope: TeamScope = Depends(get_scope)) -> Response:
    task = scope.get(Task, task_id)
    # Tasks that depended on this one are no longer waiting on anything.
    for child in scope.db.scalars(scope.select(Task).where(Task.depends_on_id == task.id)):
        child.depends_on_id = None
    scope.db.flush()
    scope.db.delete(task)
    scope.db.commit()
    return Response(status_code=204)
