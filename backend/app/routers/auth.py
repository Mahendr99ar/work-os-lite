"""Signup, login, the demo sandbox, and "who am I"."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import CurrentUser, get_current_user
from app.models import Team, User
from app.ratelimit import client_ip, demo_limiter, login_limiter
from app.schemas import SignupIn, TokenOut, UserOut
from app.security import create_token, hash_password, verify_password
from app.services.demo import create_demo_workspace

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenOut, status_code=201)
def signup(body: SignupIn, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    """Create a new team. The person who signs up becomes its first admin."""
    login_limiter.check(f"ip:{client_ip(request)}")
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This email is already registered. Log in instead.")

    team = Team(name=body.team_name)
    db.add(team)
    db.flush()  # gives the team its id before we create the user
    user = User(team_id=team.id, email=body.email, password_hash=hash_password(body.password), role="admin")
    db.add(user)
    db.commit()
    return TokenOut(access_token=create_token(user.id, team.id, user.role))


@router.post("/login", response_model=TokenOut)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenOut:
    """Standard OAuth2 form login, so the Swagger "Authorize" button works too.

    The form field is called `username`; we put the email in it.
    """
    login_limiter.check(f"ip:{client_ip(request)}")
    user = db.scalar(select(User).where(User.email == form.username.strip().lower()))
    # Same message for "no such user" and "wrong password", so emails cannot be probed.
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    return TokenOut(access_token=create_token(user.id, user.team_id, user.role))


@router.post("/demo", response_model=TokenOut, status_code=201)
def demo(request: Request, db: Session = Depends(get_db)) -> TokenOut:
    """Create a private sandbox team with sample projects, documents and a pending AI plan."""
    if not settings.demo_mode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demo is turned off on this server")
    demo_limiter.check(f"ip:{client_ip(request)}")
    user = create_demo_workspace(db)
    return TokenOut(access_token=create_token(user.id, user.team_id, user.role))


@router.get("/me", response_model=UserOut)
def me(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    user = db.get(User, current.id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    team = db.get(Team, user.team_id)
    return UserOut(id=user.id, email=user.email, role=user.role, team_id=user.team_id, team_name=team.name)
