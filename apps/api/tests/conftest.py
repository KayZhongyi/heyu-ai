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


def invite_and_accept(
    client: TestClient,
    auth: dict[str, str],
    email: str,
    role: str,
    password: str,
    display_name: str | None = None,
) -> tuple[dict, dict]:
    invitation = client.post(
        "/v1/invitations",
        headers=auth,
        json={"email": email, "role": role, "expires_in_hours": 72},
    )
    assert invitation.status_code == 201, invitation.text
    accepted = client.post(
        "/v1/invitations/accept",
        json={
            "token": invitation.json()["token"],
            "display_name": display_name or role.replace("_", " ").title(),
            "password": password,
        },
    )
    assert accepted.status_code == 200, accepted.text
    return invitation.json(), accepted.json()


@pytest.fixture()
def owner(client: TestClient):
    return bootstrap(client, "green-farm", "owner@green.example")


@pytest.fixture()
def auth(owner: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {owner['access_token']}"}
