"""Request dependencies: who is calling, and the team filter.

Endpoints never write `WHERE team_id = ...` themselves. They ask TeamScope
for data, and TeamScope adds the filter. If an endpoint forgets about teams,
it still cannot read another team's rows.
"""

from dataclasses import dataclass
from typing import TypeVar

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

M = TypeVar("M")


@dataclass(frozen=True)
class CurrentUser:
    id: int
    team_id: int
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    try:
        claims = decode_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return CurrentUser(id=int(claims["sub"]), team_id=int(claims["team_id"]), role=claims["role"])


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


class TeamScope:
    """Database access limited to the caller's team."""

    def __init__(self, db: Session, user: CurrentUser):
        self.db = db
        self.user = user
        self.team_id = user.team_id

    def select(self, model):
        return select(model).where(model.team_id == self.team_id)

    def find(self, model: type[M], obj_id: int | None) -> M | None:
        if obj_id is None:
            return None
        return self.db.scalar(self.select(model).where(model.id == obj_id))

    def get(self, model: type[M], obj_id: int) -> M:
        # Another team's row returns 404, not 403, so callers cannot even learn it exists.
        obj = self.find(model, obj_id)
        if obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
        return obj

    def add(self, obj: M) -> M:
        obj.team_id = self.team_id
        self.db.add(obj)
        return obj


def get_scope(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> TeamScope:
    return TeamScope(db, user)
