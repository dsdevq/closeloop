from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.database import Base, get_db
from app.main import app
from app.models import User


def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


@pytest.fixture(scope="function")
def client():
    """Test client authenticated as a seed admin user.

    All existing tests run as admin so ownership filters don't restrict them.
    StaticPool ensures create_all and sessions share one in-memory connection.
    """
    test_engine = _make_engine()
    Base.metadata.create_all(bind=test_engine)

    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Seed an admin user so get_current_user resolves successfully
    with TestingSession() as db:
        now = datetime.now(timezone.utc).isoformat()
        admin = User(
            email="admin@closeloop.com",
            hashed_password=hash_password("admin123"),
            role="admin",
            full_name="Test Admin",
            created_at=now,
            is_active=1,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        admin_id = admin.id

    access_token = create_access_token(admin_id)
    auth_headers = {"Authorization": f"Bearer {access_token}"}

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, headers=auth_headers) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_db, None)
    test_engine.dispose()


@pytest.fixture
def db_session(client):
    """Direct SQLAlchemy session sharing the client fixture's in-memory DB.

    Use to seed test data that has no public API endpoint yet (e.g. Notification rows
    created by trigger wiring that belongs to a later slice).

    Must be used *alongside* the client fixture so the DB override is active.
    Both fixtures share the same StaticPool engine, so data inserted here is
    immediately visible to API calls made through `client`.
    """
    override = app.dependency_overrides.get(get_db)
    assert override is not None, "db_session requires the client fixture to be active"
    gen = override()
    db = next(gen)
    try:
        yield db
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
