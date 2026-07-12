import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["APP_SECRET"] = "test-secret-that-is-at-least-thirty-two-bytes"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture()
def client(db: Session):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def bootstrap(client: TestClient, slug: str, email: str) -> dict:
    response = client.post(
        "/v1/auth/bootstrap",
        json={
            "organization_name": slug.title(),
            "organization_slug": slug,
            "email": email,
            "display_name": "Owner",
            "password": "correct-horse-battery",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def owner(client: TestClient):
    return bootstrap(client, "green-farm", "owner@green.example")


@pytest.fixture()
def auth(owner: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {owner['access_token']}"}
