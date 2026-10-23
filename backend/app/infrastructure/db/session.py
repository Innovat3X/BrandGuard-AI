from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    database_url = settings.database_url

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured. "
            "Set it in the project-root .env file."
        )

    if not database_url.startswith("postgresql+psycopg://"):
        raise RuntimeError(
            "DATABASE_URL must use the "
            "postgresql+psycopg:// scheme."
        )

    return create_engine(
        database_url,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()

    try:
        yield db
    finally:
        db.close()