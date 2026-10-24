"""SQLAlchemy async Engine, session factory, and declarative Base.

Targeting PostgreSQL via asyncpg driver.
Operations utilize async def + async with for robust resource cleanup.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.config import settings

# Hardened asynchronous engine for production resilience
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,
    pool_timeout=10,
    connect_args={
        "command_timeout": 10.0,
        "server_settings": {
            "statement_timeout": "10000",
        },
    },
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()


# FastAPI database session dependency
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
