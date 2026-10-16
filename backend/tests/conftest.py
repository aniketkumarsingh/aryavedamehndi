import os
import uuid

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://aryamehndi_app:changeme@localhost:5432/aryamehndi_test")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("OTP_DEV_MODE", "true")

import pytest
from fastapi.testclient import TestClient

import app.models  # noqa: F401 - registers every model on Base.metadata before create_all
from app.core.security import create_access_token
from app.database import Base, SessionLocal, engine, get_db
from app.main import app
from app.models.package import Package
from app.models.user import ArtistProfile, User


@pytest.fixture(scope="session", autouse=True)
def _database_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_user(db, role="consumer", phone=None, gender="female", name="Test User", is_active=True):
    phone = phone or f"9{uuid.uuid4().int % 10**9:09d}"
    user = User(phone=phone, role=role, name=name, gender=gender, is_active=is_active)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def auth_headers(user: User) -> dict:
    token = create_access_token(user.id, user.role)
    return {"Authorization": f"Bearer {token}"}


def make_package(db, package_type="regular", price_min=1000, price_max=3000, advance_amount=0):
    package = Package(
        name="Bridal Deluxe",
        package_type=package_type,
        description="Full hands and feet bridal mehndi",
        price_min=price_min,
        price_max=price_max,
        duration_minutes=120,
        advance_amount=advance_amount,
    )
    db.add(package)
    db.commit()
    db.refresh(package)
    return package


def make_approved_artist(db, gender="female", lat=28.6139, lng=77.2090):
    artist_user = make_user(db, role="artist", gender=gender, name="Test Artist")
    profile = ArtistProfile(
        user_id=artist_user.id,
        base_lat=lat,
        base_lng=lng,
        kyc_status="approved",
        consent_given=True,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return artist_user, profile


@pytest.fixture
def consumer(db):
    return make_user(db, role="consumer", gender="female", name="Priya Verma")


@pytest.fixture
def artist_with_profile(db):
    return make_approved_artist(db)


@pytest.fixture
def package(db):
    return make_package(db)
