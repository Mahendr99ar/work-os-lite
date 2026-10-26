"""Write a row to the audit log. Called for every AI call and every human review."""

from sqlalchemy.orm import Session

from app.models import AuditLog

MAX_SUMMARY = 300


def log(
    db: Session,
    *,
    team_id: int,
    user_id: int,
    action: str,
    input_text: str,
    output: str,
    status: str,
    plan_id: int | None = None,
) -> AuditLog:
    summary = input_text if len(input_text) <= MAX_SUMMARY else input_text[:MAX_SUMMARY] + "..."
    row = AuditLog(
        team_id=team_id,
        user_id=user_id,
        action=action,
        input_summary=summary,
        output=output,
        status=status,
        plan_id=plan_id,
    )
    db.add(row)
    return row
