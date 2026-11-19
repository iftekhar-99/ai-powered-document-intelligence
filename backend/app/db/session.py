import logging
import socket
from typing import AsyncGenerator, Tuple
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import settings
from app.db.base import Base

logger = logging.getLogger("doc_intel.db")


def is_postgres_accessible(host: str, port: int, timeout: float = 0.5) -> bool:
    """Check whether PostgreSQL port is open and accepting socket connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def get_effective_database_urls() -> Tuple[str, str, str]:
    """
    Determine the active async and sync database connection URLs.
    Falls back to SQLite for local development if PostgreSQL is unreachable.
    Returns: (async_url, sync_url, database_provider)
    """
    if settings.DATABASE_URL.startswith("postgresql"):
        if is_postgres_accessible(settings.POSTGRES_SERVER, settings.POSTGRES_PORT):
            return settings.DATABASE_URL, settings.DATABASE_URL_SYNC, "postgresql"
        elif settings.USE_SQLITE_FALLBACK:
            sqlite_async = f"sqlite+aiosqlite:///{settings.SQLITE_DB_PATH}"
            sqlite_sync = f"sqlite:///{settings.SQLITE_DB_PATH}"
            logger.warning(
                "PostgreSQL at %s:%s is unreachable. Falling back to SQLite local database (%s)",
                settings.POSTGRES_SERVER,
                settings.POSTGRES_PORT,
                sqlite_async,
            )
            return sqlite_async, sqlite_sync, "sqlite"

    # Default to configured settings
    is_sqlite = "sqlite" in settings.DATABASE_URL
    provider = "sqlite" if is_sqlite else "postgresql"
    return settings.DATABASE_URL, settings.DATABASE_URL_SYNC, provider


ASYNC_DB_URL, SYNC_DB_URL, DB_PROVIDER = get_effective_database_urls()

# Engine creation
engine_kwargs = {"echo": False, "future": True}
if DB_PROVIDER == "sqlite":
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine: AsyncEngine = create_async_engine(ASYNC_DB_URL, **engine_kwargs)

# Enable foreign key constraints in SQLite
if DB_PROVIDER == "sqlite":
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for yielding database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables defined in Base metadata if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema initialized using %s provider (%s)", DB_PROVIDER, ASYNC_DB_URL)
