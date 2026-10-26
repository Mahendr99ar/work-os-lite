"""Project CRUD. Every query goes through TeamScope."""

from fastapi import APIRouter, Depends, Response

from app.deps import TeamScope, get_scope, require_admin
from app.models import AuditLog, Plan, Project
from app.schemas import ProjectIn, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, scope: TeamScope = Depends(get_scope)) -> Project:
    project = scope.add(Project(name=body.name, description=body.description))
    scope.db.commit()
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(scope: TeamScope = Depends(get_scope)) -> list[Project]:
    return list(scope.db.scalars(scope.select(Project).order_by(Project.id)))


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, scope: TeamScope = Depends(get_scope)) -> Project:
    return scope.get(Project, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectUpdate, scope: TeamScope = Depends(get_scope)) -> Project:
    project = scope.get(Project, project_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    scope.db.commit()
    return project


@router.delete("/{project_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_project(project_id: int, scope: TeamScope = Depends(get_scope)) -> Response:
    project = scope.get(Project, project_id)
    # Plans point at the project, so they go first. Audit rows are kept; they just lose the plan link.
    # Tasks are removed by the cascade on Project.tasks.
    for plan in scope.db.scalars(scope.select(Plan).where(Plan.project_id == project.id)):
        for row in scope.db.scalars(scope.select(AuditLog).where(AuditLog.plan_id == plan.id)):
            row.plan_id = None
        scope.db.delete(plan)
    for task in project.tasks:
        task.depends_on_id = None
    scope.db.flush()
    scope.db.delete(project)
    scope.db.commit()
    return Response(status_code=204)
