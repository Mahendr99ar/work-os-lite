"""Request and response shapes. Pydantic rejects bad input before it reaches the database."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TaskStatus = Literal["todo", "in_progress", "done", "blocked"]


def _clean_email(value: str) -> str:
    value = value.strip().lower()
    if "@" not in value or "." not in value.split("@")[-1]:
        raise ValueError("not a valid email")
    return value


# ---------- auth and team ----------

class SignupIn(BaseModel):
    team_name: str = Field(min_length=2, max_length=100)
    email: str
    password: str = Field(min_length=8, max_length=128)

    _email = field_validator("email")(_clean_email)


class MemberIn(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    role: Literal["admin", "member"] = "member"

    _email = field_validator("email")(_clean_email)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str
    team_id: int
    team_name: str | None = None


# ---------- projects and tasks ----------

class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    created_at: datetime


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    status: TaskStatus = "todo"
    assignee_id: int | None = None
    due_date: date | None = None
    depends_on_id: int | None = None


class TaskUpdate(BaseModel):
    """Every field is optional. Only the fields sent in the request are changed."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: TaskStatus | None = None
    assignee_id: int | None = None
    due_date: date | None = None
    depends_on_id: int | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    description: str
    status: str
    assignee_id: int | None
    due_date: date | None
    depends_on_id: int | None


class BlockedTaskOut(BaseModel):
    task: TaskOut
    reason: str
    blocked_by: TaskOut | None


# ---------- documents and RAG ----------

class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    chunk_count: int
    created_at: datetime


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class SourceOut(BaseModel):
    document_id: int
    filename: str
    similarity: float


class AskOut(BaseModel):
    answer: str
    sources: list[SourceOut]
    refused: bool


# ---------- AI planner ----------

class PlannedTask(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    depends_on: int | None = Field(default=None, description="1-based number of an earlier task in this plan")
    estimate_days: int | None = Field(default=None, ge=1, le=60)


class TaskPlan(BaseModel):
    """The exact JSON shape the LLM must return."""

    tasks: list[PlannedTask] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def dependencies_point_backwards(self) -> "TaskPlan":
        # A task may only depend on a task listed before it. This also rules out cycles.
        for number, task in enumerate(self.tasks, start=1):
            if task.depends_on is not None and not 1 <= task.depends_on < number:
                raise ValueError(f"task {number} has depends_on={task.depends_on}; it must point to an earlier task")
        return self


class PlanIn(BaseModel):
    project_id: int
    brief: str = Field(min_length=20, max_length=8000)


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_by: int
    brief: str
    plan_json: dict
    status: str
    reviewed_by: int | None
    created_at: datetime


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    action: str
    input_summary: str
    output: str
    status: str
    plan_id: int | None
    created_at: datetime
