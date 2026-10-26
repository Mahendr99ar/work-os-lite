"""AI planner. The AI suggests a plan; only an admin can turn it into real tasks."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import TeamScope, get_scope, require_admin
from app.models import AuditLog, Plan, Project, Task
from app.schemas import PlanIn, PlanOut, TaskOut, TaskPlan
from app.services import audit
from app.ratelimit import plan_limiter
from app.services.llm import LLMError, LLMNotConfigured
from app.services.planner import PlanGenerationError, generate_plan

router = APIRouter(prefix="/planner", tags=["planner"])


@router.post("/plans", response_model=PlanOut, status_code=201)
def create_plan(body: PlanIn, scope: TeamScope = Depends(get_scope)) -> Plan:
    scope.get(Project, body.project_id)
    plan_limiter.check(f"user:{scope.user.id}")
    log_args = dict(team_id=scope.team_id, user_id=scope.user.id, action="plan_generate", input_text=body.brief)

    try:
        plan_data, raw_outputs = generate_plan(body.brief)
    except PlanGenerationError as exc:
        audit.log(scope.db, **log_args, output="\n---\n".join(exc.raw_outputs), status="failed")
        scope.db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "The AI returned an invalid plan twice. Try rewording the brief.")
    except LLMError as exc:
        audit.log(scope.db, **log_args, output=str(exc), status="failed")
        scope.db.commit()
        if isinstance(exc, LLMNotConfigured):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                                "AI is not set up on this server. The admin needs to add LLM_API_KEY.")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"The AI service failed: {exc}")

    plan = scope.add(Plan(project_id=body.project_id, created_by=scope.user.id, brief=body.brief,
                          plan_json=plan_data.model_dump(), status="pending"))
    scope.db.flush()
    audit.log(scope.db, **log_args, output="\n---\n".join(raw_outputs), status="pending", plan_id=plan.id)
    scope.db.commit()
    return plan


@router.get("/plans", response_model=list[PlanOut])
def list_plans(
    status_filter: str | None = Query(default=None, alias="status"),
    scope: TeamScope = Depends(get_scope),
) -> list[Plan]:
    query = scope.select(Plan).order_by(Plan.id.desc())
    if status_filter:
        query = query.where(Plan.status == status_filter)
    return list(scope.db.scalars(query))


@router.get("/plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: int, scope: TeamScope = Depends(get_scope)) -> Plan:
    return scope.get(Plan, plan_id)


def _review(scope: TeamScope, plan: Plan, decision: str) -> None:
    """Mark the plan and its original audit row, and log who made the decision."""
    plan.status = decision
    plan.reviewed_by = scope.user.id
    plan.reviewed_at = datetime.now(timezone.utc)
    for row in scope.db.scalars(scope.select(AuditLog).where(AuditLog.plan_id == plan.id,
                                                             AuditLog.action == "plan_generate")):
        row.status = decision
    audit.log(scope.db, team_id=scope.team_id, user_id=scope.user.id, action="plan_review",
              input_text=f"plan {plan.id}", output=decision, status=decision, plan_id=plan.id)


def _pending_plan(scope: TeamScope, plan_id: int) -> Plan:
    plan = scope.get(Plan, plan_id)
    if plan.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Plan is already {plan.status}")
    return plan


@router.post("/plans/{plan_id}/approve", response_model=list[TaskOut], dependencies=[Depends(require_admin)])
def approve_plan(plan_id: int, scope: TeamScope = Depends(get_scope)) -> list[Task]:
    plan = _pending_plan(scope, plan_id)
    scope.get(Project, plan.project_id)
    # Validate again: the stored JSON is checked at the moment it becomes real data.
    plan_data = TaskPlan.model_validate(plan.plan_json)

    created: list[Task] = []
    for item in plan_data.tasks:
        parent = created[item.depends_on - 1] if item.depends_on else None
        description = item.description
        if item.estimate_days:
            description = f"{description}\n\nEstimate: {item.estimate_days} day(s)".strip()
        task = scope.add(Task(project_id=plan.project_id, title=item.title, description=description,
                              status="todo", depends_on_id=parent.id if parent else None))
        scope.db.flush()  # assigns task.id so later tasks can depend on it
        created.append(task)

    _review(scope, plan, "approved")
    scope.db.commit()
    return created


@router.post("/plans/{plan_id}/reject", response_model=PlanOut, dependencies=[Depends(require_admin)])
def reject_plan(plan_id: int, scope: TeamScope = Depends(get_scope)) -> Plan:
    plan = _pending_plan(scope, plan_id)
    _review(scope, plan, "rejected")
    scope.db.commit()
    return plan
