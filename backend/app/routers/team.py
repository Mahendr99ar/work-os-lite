"""Team members. Admins add people; everyone in the team can see the list."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.deps import TeamScope, get_scope, require_admin
from app.models import User
from app.schemas import MemberIn, UserOut
from app.security import hash_password

router = APIRouter(prefix="/team", tags=["team"])


@router.get("/members", response_model=list[UserOut])
def list_members(scope: TeamScope = Depends(get_scope)) -> list[User]:
    return list(scope.db.scalars(scope.select(User).order_by(User.id)))


@router.post("/members", response_model=UserOut, status_code=201, dependencies=[Depends(require_admin)])
def add_member(body: MemberIn, scope: TeamScope = Depends(get_scope)) -> User:
    # Emails are unique across all teams, so this check is global on purpose.
    if scope.db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")
    user = scope.add(User(email=body.email, password_hash=hash_password(body.password), role=body.role))
    scope.db.commit()
    return user
