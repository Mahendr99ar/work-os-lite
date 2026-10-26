"""Database engine and session.

Production runs on PostgreSQL with pgvector. Tests can also run on SQLite,
so the app works on a laptop with no database installed.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def _make_engine(url: str):
    # Render gives "postgres://" URLs; SQLAlchemy needs the psycopg driver name.
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("sqlite"):
        # FastAPI may use the session from another thread, so SQLite must allow it.
        return create_engine(url, connect_args={"check_same_thread": False})
    # pre_ping and recycle matter on free hosts: Neon suspends idle databases and
    # drops their connections, so stale ones must be detected and replaced.
    return create_engine(url, pool_pre_ping=True, pool_recycle=300, pool_size=5, max_overflow=5)


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def is_postgres() -> bool:
    return engine.dialect.name == "postgresql"


def init_db() -> None:
    """Create the pgvector extension (Postgres only) and all tables."""
    from app import models  # noqa: F401  (registers the tables on Base)

    if is_postgres():
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
