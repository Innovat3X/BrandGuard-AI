import os
from collections.abc import Generator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


@pytest.fixture(scope="session")
def postgres_test_engine() -> Generator[Engine, None, None]:
    database_url = os.getenv("TEST_DATABASE_URL")

    if not database_url:
        pytest.fail(
            "TEST_DATABASE_URL is required for PostgreSQL integration "
            "tests. Configure it to use a dedicated *_test database."
        )

    url = make_url(database_url)

    if not url.database or not url.database.endswith("_test"):
        pytest.fail(
            "Safety check failed: TEST_DATABASE_URL must target a "
            "database whose name ends with '_test'."
        )

    if url.drivername != "postgresql+psycopg":
        pytest.fail(
            "TEST_DATABASE_URL must use postgresql+psycopg://."
        )

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(
    postgres_test_engine: Engine,
) -> Generator[Session, None, None]:
    connection = postgres_test_engine.connect()
    outer_transaction = connection.begin()

    session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()