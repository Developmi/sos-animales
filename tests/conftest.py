"""Shared pytest fixtures across all domain test suites."""

import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.database import Base


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    # Use TEST_DATABASE_URL if defined, otherwise fallback to settings.DATABASE_URL
    test_db_url = os.getenv("TEST_DATABASE_URL", settings.DATABASE_URL)
    engine = create_async_engine(test_db_url, echo=False)

    # Create tables if not existing (checkfirst=True)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(sync_conn, checkfirst=True)
        )

    yield engine

    # Dispose of engine connection pool after tests
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """
    Creates an isolated database session for each test.
    Performs rollback at teardown to prevent test data persistence.
    """
    connection = await engine.connect()
    # Begin a global transaction for this test
    transaction = await connection.begin()

    AsyncSessionTest = async_sessionmaker(
        bind=connection, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionTest() as session:
        yield session

    # Roll back all changes made during the test execution
    await transaction.rollback()
    await connection.close()
