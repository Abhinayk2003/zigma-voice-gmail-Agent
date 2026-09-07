from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings


# =========================================================
# Settings
# =========================================================

settings = get_settings()


# =========================================================
# Database Engine
# =========================================================

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
)


# =========================================================
# Database Session Factory
# =========================================================

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


# =========================================================
# Database Dependency
# =========================================================

def get_db() -> Generator[Session, None, None]:
    """
    Provide a SQLAlchemy database session.

    The session is automatically closed after the request
    finishes.
    """

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()