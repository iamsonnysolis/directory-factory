"""Database configuration and session management."""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/collector.db")

# Convert sync sqlite:// to async
if DATABASE_URL.startswith("sqlite://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://")
else:
    ASYNC_DATABASE_URL = DATABASE_URL

# SQLite needs check_same_thread=False and timeout for concurrent access
# pool_pre_ping helps with connection reuse
if "sqlite" in ASYNC_DATABASE_URL:
    engine = create_async_engine(
        ASYNC_DATABASE_URL,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False, "timeout": 30.0},
        pool_pre_ping=True
    )
else:
    engine = create_async_engine(
        ASYNC_DATABASE_URL,
        echo=False,
        future=True
    )

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)


async def get_db():
    """Dependency for FastAPI to get async database session."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Create all tables."""
    from models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database engine."""
    await engine.dispose()