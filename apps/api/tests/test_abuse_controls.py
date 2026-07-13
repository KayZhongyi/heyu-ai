from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

from fastapi import HTTPException, Request
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.abuse import client_network_identity, enforce_limit
from app.config import Settings, get_settings
from app.database import Base
from app.models import AbuseLimitBucket, Organization


def limited_settings(**overrides) -> Settings:
    values = {
        "app_secret": "test-secret-that-is-at-least-thirty-two-bytes",
        "login_limit_attempts": 2,
        "login_limit_window_seconds": 300,
        "bootstrap_limit_attempts": 2,
        "bootstrap_limit_window_seconds": 300,
        "invitation_create_limit_attempts": 2,
        "invitation_create_limit_window_seconds": 300,
        "invitation_inspect_limit_attempts": 2,
        "invitation_inspect_limit_window_seconds": 300,
        "invitation_accept_limit_attempts": 2,
        "invitation_accept_limit_window_seconds": 300,
    }
    values.update(overrides)
    return Settings(**values)


def settings_override(settings: Settings):
    return lambda: settings


def login_payload(email="owner@green.example", password="wrong-password"):
    return {
        "organization_slug": "green-farm",
        "email": email,
        "password": password,
    }


def test_login_limit_blocks_bad_and_then_correct_password(client, owner):
    settings = limited_settings()
    client.app.dependency_overrides[get_settings] = settings_override(settings)

    for _ in range(2):
        response = client.post("/v1/auth/login", json=login_payload())
        assert response.status_code == 401

    blocked = client.post(
        "/v1/auth/login",
        json=login_payload(password="correct-horse-battery"),
    )
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert blocked.headers["cache-control"] == "no-store"
    assert blocked.json()["detail"] == "Too many requests. Please try again later."


def test_login_limit_normalizes_email_and_does_not_reveal_account(client, owner):
    settings = limited_settings()
    client.app.dependency_overrides[get_settings] = settings_override(settings)

    first = client.post("/v1/auth/login", json=login_payload(" OWNER@GREEN.EXAMPLE "))
    second = client.post("/v1/auth/login", json=login_payload("owner@green.example"))
    blocked = client.post("/v1/auth/login", json=login_payload("Owner@Green.Example"))

    assert first.status_code == second.status_code == 401
    assert blocked.status_code == 429


def test_login_targets_are_isolated_when_network_limit_is_higher(client, owner):
    settings = limited_settings(login_limit_attempts=2)
    client.app.dependency_overrides[get_settings] = settings_override(settings)

    for email in ("one@example.com", "two@example.com"):
        first = client.post("/v1/auth/login", json=login_payload(email))
        second = client.post("/v1/auth/login", json=login_payload(email))
        assert first.status_code == second.status_code == 401


def test_bootstrap_is_limited_and_subject_data_is_hmac_protected(client, db):
    settings = limited_settings(bootstrap_limit_attempts=1)
    client.app.dependency_overrides[get_settings] = settings_override(settings)
    email = "sensitive-bootstrap@example.com"
    payload = {
        "organization_name": "First Bootstrap",
        "organization_slug": "first-bootstrap",
        "email": email,
        "display_name": "Owner",
        "password": "correct-horse-battery",
    }

    assert client.post("/v1/auth/bootstrap", json=payload).status_code == 201
    payload["organization_slug"] = "second-bootstrap"
    payload["email"] = "another-bootstrap@example.com"
    blocked = client.post("/v1/auth/bootstrap", json=payload)
    assert blocked.status_code == 429

    buckets = db.scalars(select(AbuseLimitBucket)).all()
    assert buckets
    serialized = " ".join(f"{bucket.scope} {bucket.subject_hash}" for bucket in buckets)
    assert email not in serialized
    assert "testclient" not in serialized
    assert all(len(bucket.subject_hash) == 64 for bucket in buckets)


def test_invitation_inspect_and_accept_are_limited(client):
    settings = limited_settings(
        invitation_inspect_limit_attempts=1,
        invitation_accept_limit_attempts=1,
    )
    client.app.dependency_overrides[get_settings] = settings_override(settings)
    token = "not-a-real-invitation-token-123456789"

    assert client.post("/v1/invitations/inspect", json={"token": token}).status_code == 404
    inspect_blocked = client.post("/v1/invitations/inspect", json={"token": token})
    assert inspect_blocked.status_code == 429
    assert inspect_blocked.headers["cache-control"] == "no-store"

    accept_payload = {
        "token": token,
        "display_name": "Invitee",
        "password": "correct-horse-battery",
    }
    assert client.post("/v1/invitations/accept", json=accept_payload).status_code == 404
    accept_blocked = client.post("/v1/invitations/accept", json=accept_payload)
    assert accept_blocked.status_code == 429
    assert accept_blocked.headers["cache-control"] == "no-store"


def test_invitation_creation_is_limited_per_actor_and_organization(client, auth):
    settings = limited_settings(invitation_create_limit_attempts=1)
    client.app.dependency_overrides[get_settings] = settings_override(settings)

    first = client.post(
        "/v1/invitations",
        headers=auth,
        json={"email": "first@example.com", "role": "creator"},
    )
    blocked = client.post(
        "/v1/invitations",
        headers=auth,
        json={"email": "second@example.com", "role": "creator"},
    )

    assert first.status_code == 201
    assert blocked.status_code == 429


def request_from(peer: str, forwarded: str | None = None) -> Request:
    headers = []
    if forwarded:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": headers,
            "client": (peer, 12345),
            "server": ("test", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_forwarded_for_is_ignored_without_a_trusted_proxy():
    settings = limited_settings(trusted_proxy_cidrs="")
    request = request_from("198.51.100.20", "203.0.113.7")
    assert client_network_identity(request, settings) == "198.51.100.20"


def test_forwarded_for_is_resolved_only_through_trusted_proxies():
    settings = limited_settings(trusted_proxy_cidrs="10.0.0.0/8,192.0.2.10/32")
    request = request_from("10.0.0.8", "203.0.113.7, 192.0.2.10")
    assert client_network_identity(request, settings) == "203.0.113.7"


def test_bucket_expires_at_the_next_fixed_window(db):
    settings = limited_settings()
    first_window = datetime(2026, 7, 14, 0, 0, tzinfo=UTC)
    enforce_limit(
        db,
        settings,
        scope="test.expiry",
        subjects=["network:example"],
        attempts=1,
        window_seconds=60,
        now=first_window,
    )

    enforce_limit(
        db,
        settings,
        scope="test.expiry",
        subjects=["network:example"],
        attempts=1,
        window_seconds=60,
        now=first_window + timedelta(seconds=60),
    )
    assert len(db.scalars(select(AbuseLimitBucket)).all()) == 2


def test_sqlite_concurrent_limit_consumption_is_atomic(tmp_path):
    database_path = tmp_path / "concurrent-abuse.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = limited_settings()
    attempts = 4
    workers = 8
    barrier = Barrier(workers)
    now = datetime(2026, 7, 14, 0, 0, tzinfo=UTC)
    with factory() as session:
        enforce_limit(
            session,
            settings,
            scope="test.concurrent",
            subjects=["network:shared"],
            attempts=attempts,
            window_seconds=60,
            now=now,
        )

    def consume_once() -> int:
        barrier.wait()
        with factory() as session:
            try:
                enforce_limit(
                    session,
                    settings,
                    scope="test.concurrent",
                    subjects=["network:shared"],
                    attempts=attempts,
                    window_seconds=60,
                    now=now,
                )
            except HTTPException as error:
                return error.status_code
        return 200

    with ThreadPoolExecutor(max_workers=workers) as pool:
        statuses = list(pool.map(lambda _: consume_once(), range(workers)))

    assert statuses.count(200) == attempts - 1
    assert statuses.count(429) == workers - (attempts - 1)
    with factory() as session:
        bucket = session.scalar(select(AbuseLimitBucket))
        assert bucket is not None
        assert bucket.request_count == attempts


def test_limiter_does_not_commit_or_rollback_business_session(tmp_path):
    database_path = tmp_path / "transaction-isolation.db"
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = limited_settings()
    now = datetime(2026, 7, 14, 0, 0, tzinfo=UTC)

    with factory() as business_db:
        organization = Organization(name="Uncommitted Farm", slug="uncommitted-farm")
        business_db.add(organization)

        enforce_limit(
            business_db,
            settings,
            scope="test.transaction",
            subjects=["network:shared"],
            attempts=1,
            window_seconds=60,
            now=now,
        )
        with factory() as observer:
            assert (
                observer.scalar(select(Organization).where(Organization.slug == "uncommitted-farm"))
                is None
            )

        try:
            enforce_limit(
                business_db,
                settings,
                scope="test.transaction",
                subjects=["network:shared"],
                attempts=1,
                window_seconds=60,
                now=now,
            )
        except HTTPException as error:
            assert error.status_code == 429
        else:
            raise AssertionError("Expected the limiter to reject the second request")

        assert organization in business_db.new
        business_db.commit()

    with factory() as observer:
        assert (
            observer.scalar(select(Organization).where(Organization.slug == "uncommitted-farm"))
            is not None
        )
