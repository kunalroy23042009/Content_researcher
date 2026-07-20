"""
Tests for authentication router.
"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import create_engine, Session, SQLModel
from sqlmodel.pool import StaticPool


@pytest.fixture
def client():
    """Create a test client with an in-memory database."""
    from app.main import app
    from app import db as db_module

    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(test_engine)

    def get_test_session():
        with Session(test_engine) as session:
            yield session

    db_module._engine = test_engine

    with TestClient(app) as c:
        yield c


def test_register_and_login(client):
    # Register
    resp = client.post("/api/auth/register", json={"email": "test@example.com", "password": "password123"})
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "test@example.com"
    assert data["user"]["plan"] == "free"


def test_register_duplicate_email(client):
    client.post("/api/auth/register", json={"email": "dupe@example.com", "password": "pass123"})
    resp = client.post("/api/auth/register", json={"email": "dupe@example.com", "password": "pass123"})
    assert resp.status_code == 400


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={"email": "user@example.com", "password": "correct"})
    resp = client.post("/api/auth/login", json={"email": "user@example.com", "password": "wrong"})
    assert resp.status_code == 401


def test_get_me(client):
    reg = client.post("/api/auth/register", json={"email": "me@example.com", "password": "pass"})
    token = reg.json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"


def test_protected_without_token(client):
    resp = client.post("/analyze-channel", json={"channel_url": "https://youtube.com/@test"})
    assert resp.status_code == 401
