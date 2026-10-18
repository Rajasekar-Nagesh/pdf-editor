"""Database engine and session management (SQLAlchemy 2.x)."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_connect_args = {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
engine = create_engine(_settings.database_url, pool_pre_ping=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a DB session that is always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(attempts: int = 10) -> None:
    """Create tables if they do not exist. Imported models register themselves on Base.

    Several containers (api workers, job workers, scheduler) start at once, so we retry: the database
    may still be starting, or another process may be creating the same tables concurrently.
    """
    import time

    from . import models  # noqa: F401

    for attempt in range(1, attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(min(2 * attempt, 10))
