"""AI planner. The AI suggests a plan; only an admin can turn it into real tasks."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import update

from app.deps import TeamScope, get_scope, require_admin
from app.models import Plan, Project, Task
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
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"The AI service failed: {exc.public_message}")

    plan = scope.add(Plan(project_id=body.project_id, created_by=scope.user.id, brief=body.brief,
                          plan_json=plan_data.model_dump(), status="pending"))
    scope.db.flush()
    audit.log(scope.db, **log_args, output="\n---\n".join(raw_outputs), status="ok", plan_id=plan.id)
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


def _claim_for_review(scope: TeamScope, plan_id: int, decision: str) -> Plan:
    """Move a plan from pending to `decision` in one conditional UPDATE.

    The UPDATE only matches while the plan is still pending. If two requests
    arrive together (a double click, two admins), the database lets one of
    them change the row; the other matches nothing and gets 409. Checking the
    status in Python first and writing later would let both through.
    """
    plan = scope.get(Plan, plan_id)  # 404 for a plan in another team
    result = scope.db.execute(
        update(Plan)
        .where(Plan.id == plan.id, Plan.team_id == scope.team_id, Plan.status == "pending")
        .values(status=decision, reviewed_by=scope.user.id, reviewed_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        scope.db.rollback()
        scope.db.refresh(plan)
        raise HTTPException(status.HTTP_409_CONFLICT, f"Plan is already {plan.status}")
    scope.db.refresh(plan)
    # The audit log is append-only: the review gets its own row, earlier rows are never edited.
    audit.log(scope.db, team_id=scope.team_id, user_id=scope.user.id, action="plan_review",
              input_text=f"plan {plan.id}", output=decision, status=decision, plan_id=plan.id)
    return plan


@router.post("/plans/{plan_id}/approve", response_model=list[TaskOut], dependencies=[Depends(require_admin)])
def approve_plan(plan_id: int, scope: TeamScope = Depends(get_scope)) -> list[Task]:
    plan = _claim_for_review(scope, plan_id, "approved")
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

    # One commit for the status change and every task. If anything above fails,
    # nothing is committed and the plan stays pending.
    scope.db.commit()
    return created


@router.post("/plans/{plan_id}/reject", response_model=PlanOut, dependencies=[Depends(require_admin)])
def reject_plan(plan_id: int, scope: TeamScope = Depends(get_scope)) -> Plan:
    plan = _claim_for_review(scope, plan_id, "rejected")
    scope.db.commit()
    return plan
