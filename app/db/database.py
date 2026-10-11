"""DB layer — engine, session, and init."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import settings
from app.db.tables import Base, Doctor

engine = create_engine(
    settings.database_url,
    echo=settings.db_echo,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)


@event.listens_for(engine, "connect")
def _sqlite_fk_on(dbapi_conn, _):
    if settings.database_url.startswith("sqlite"):
        dbapi_conn.execute("PRAGMA foreign_keys = ON")


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """One unit of work: commit on success, rollback on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


SEED_DOCTORS = [
    ("Dr. Anjali Mehta", "General Physician"),
    ("Dr. Rohan Desai", "Pediatrician"),
    ("Dr. Priya Kulkarni", "Gynecologist"),
]


def init_db() -> None:
    Base.metadata.create_all(engine)
    with session_scope() as s:
        if not s.query(Doctor).first():
            s.add_all(Doctor(name=n, specialty=sp) for n, sp in SEED_DOCTORS)