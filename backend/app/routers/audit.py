"""Read the audit log. Admins only."""

from fastapi import APIRouter, Depends, Query

from app.deps import TeamScope, get_scope, require_admin
from app.models import AuditLog
from app.schemas import AuditOut

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[AuditOut])
def list_audit(limit: int = Query(default=100, ge=1, le=500), scope: TeamScope = Depends(get_scope)) -> list[AuditLog]:
    return list(scope.db.scalars(scope.select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)))
