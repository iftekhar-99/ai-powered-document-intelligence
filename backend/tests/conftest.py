import os
import shutil
import tempfile
from typing import AsyncGenerator, Generator
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
import app.db.session as db_session_mod
import app.workers.celery_app as celery_mod
import app.services.extraction.service as ext_service_mod
from app.main import app
from app.services.document_processing.storage import storage_service


@pytest.fixture(scope="session")
def test_upload_dir() -> Generator[str, None, None]:
    temp_dir = tempfile.mkdtemp(prefix="test_uploads_")
    old_dir = storage_service.upload_dir
    storage_service.upload_dir = temp_dir
    yield temp_dir
    storage_service.upload_dir = old_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def clean_upload_dir(test_upload_dir: str) -> Generator[str, None, None]:
    # Ensure empty directory before each test
    for item in os.listdir(test_upload_dir):
        path = os.path.join(test_upload_dir, item)
        if os.path.isfile(path):
            os.unlink(path)
        elif os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
    yield test_upload_dir


@pytest.fixture
def client(clean_upload_dir: str) -> Generator[TestClient, None, None]:
    # Create an isolated SQLite database file per test
    db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = db_file.name
    db_file.close()

    # Create tables synchronously using standard SQLite engine
    from sqlalchemy import create_engine
    sync_engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    test_async_url = f"sqlite+aiosqlite:///{db_path}"
    test_engine = create_async_engine(
        test_async_url,
        connect_args={"check_same_thread": False},
        future=True,
    )

    @event.listens_for(test_engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    test_session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_maker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db

    from sqlalchemy.orm import sessionmaker
    test_sync_engine = create_engine(f"sqlite:///{db_path}")
    @event.listens_for(test_sync_engine, "connect")
    def set_sync_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    test_sync_session_factory = sessionmaker(test_sync_engine, expire_on_commit=False)

    with TestClient(app) as test_client:
        test_client.db_path = db_path
        test_client.sync_session_factory = test_sync_session_factory
        yield test_client

    test_sync_engine.dispose()
    app.dependency_overrides.clear()
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<< /Title (Invoice) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


@pytest.fixture
def png_bytes() -> bytes:
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"


@pytest.fixture
def jpg_bytes() -> bytes:
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\xff\xd9"


@pytest.fixture
def tiff_bytes() -> bytes:
    return b"II*\x00\x08\x00\x00\x00\x00\x00test_tiff_content"


@pytest.fixture
def xlsx_bytes() -> bytes:
    return b"PK\x03\x04\x14\x00\x00\x00\x08\x00sample_xlsx_binary"


@pytest.fixture
def xls_bytes() -> bytes:
    return b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1sample_xls_binary"


@pytest.fixture
def csv_bytes() -> bytes:
    return b"InvoiceNumber,Date,Amount\nINV-2026-001,2026-01-15,4500.00\n"
