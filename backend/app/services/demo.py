"""Build a ready-made sandbox workspace for "Try the demo".

Every visitor gets their own team, so one visitor's edits never show up for the
next. This also shows the team isolation working: each sandbox is just another
team_id in the same tables.
"""

import secrets
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Plan, Project, Task, Team, User
from app.security import hash_password
from app.services.ingest import ingest

DEMO_DOCS = Path(__file__).resolve().parent.parent / "demo_docs"

# A plan the AI "suggested", so visitors can try approve/reject without an API key.
SAMPLE_PLAN = {
    "tasks": [
        {"title": "Write the launch announcement", "description": "Blog post and email to existing users", "depends_on": None, "estimate_days": 2},
        {"title": "Record a 60-second demo video", "description": "Show signup, checkout and order tracking", "depends_on": None, "estimate_days": 2},
        {"title": "Schedule social posts for launch day", "description": "Use the video and the announcement", "depends_on": 2, "estimate_days": 1},
        {"title": "Brief the support team on new flows", "description": "Payments and order tracking FAQs", "depends_on": 1, "estimate_days": 1},
    ]
}
SAMPLE_BRIEF = (
    "Marketing for the 1 Dec mobile launch: we need an announcement, a short demo video, social posts on "
    "launch day using the video, and the support team must know the new flows before customers ask."
)


def create_demo_workspace(db: Session) -> User:
    today = date.today()
    tag = secrets.token_hex(4)

    team = Team(name="Acme Mobile (demo)")
    db.add(team)
    db.flush()

    admin = User(team_id=team.id, email=f"demo-{tag}@demo.workos.dev", role="admin",
                 password_hash=hash_password(secrets.token_urlsafe(24)))
    priya = User(team_id=team.id, email=f"priya-{tag}@demo.workos.dev", role="member",
                 password_hash=hash_password(secrets.token_urlsafe(24)))
    arjun = User(team_id=team.id, email=f"arjun-{tag}@demo.workos.dev", role="member",
                 password_hash=hash_password(secrets.token_urlsafe(24)))
    db.add_all([admin, priya, arjun])
    db.flush()

    launch = Project(team_id=team.id, name="Mobile app launch", description="Ship the Android and iOS app on 1 Dec")
    website = Project(team_id=team.id, name="Website refresh", description="New pricing page and docs")
    db.add_all([launch, website])
    db.flush()

    def task(project: Project, title: str, status: str, *, who: User | None = None,
             due_in: int | None = None, after: Task | None = None, description: str = "") -> Task:
        t = Task(team_id=team.id, project_id=project.id, title=title, status=status, description=description,
                 assignee_id=who.id if who else None,
                 due_date=today + timedelta(days=due_in) if due_in is not None else None,
                 depends_on_id=after.id if after else None)
        db.add(t)
        db.flush()
        return t

    spec = task(launch, "Finalise acceptance criteria", "done", who=priya, due_in=-6)
    auth = task(launch, "Build auth service", "in_progress", who=arjun, due_in=-1, after=spec,
                description="Email login, OTP fallback, refresh tokens")
    task(launch, "Payments API", "todo", who=arjun, due_in=6, after=auth, description="Razorpay test mode first")
    task(launch, "Order tracking screen", "todo", who=priya, due_in=9, after=auth)
    task(launch, "App store listing", "blocked", who=priya, due_in=4,
         description="Waiting for final screenshots from design")
    task(launch, "Crash reporting setup", "done", who=arjun, due_in=-3)
    task(website, "New pricing page copy", "in_progress", who=priya, due_in=3)
    task(website, "Migrate docs to new theme", "todo", due_in=12)

    for path in sorted(DEMO_DOCS.glob("*.md")):
        ingest(db, team_id=team.id, user_id=admin.id, filename=path.name, data=path.read_bytes())

    db.add(Plan(team_id=team.id, project_id=launch.id, created_by=priya.id, brief=SAMPLE_BRIEF,
                plan_json=SAMPLE_PLAN, status="pending"))
    db.commit()
    return admin
