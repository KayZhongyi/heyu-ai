from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditEvent, OrganizationInvitation, User
from tests.conftest import bootstrap, invite_and_accept


def test_owner_can_add_member_and_role_is_enforced(client, auth):
    invitation, accepted = invite_and_accept(
        client,
        auth,
        "creator@example.com",
        "creator",
        "creator-password",
        "Content Creator",
    )
    assert invitation["role"] == "creator"
    assert accepted["access_token"]

    members = client.get("/v1/members", headers=auth)
    assert members.status_code == 200
    assert {item["email"] for item in members.json()} == {
        "owner@green.example",
        "creator@example.com",
    }

    login = client.post(
        "/v1/auth/login",
        json={
            "organization_slug": "green-farm",
            "email": "creator@example.com",
            "password": "creator-password",
        },
    )
    assert login.status_code == 200
    creator_auth = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/v1/members", headers=creator_auth).status_code == 403
    assert (
        client.post(
            "/v1/brands",
            headers=creator_auth,
            json={"name": "Forbidden brand", "story": "", "voice": ""},
        ).status_code
        == 403
    )
    brand = client.post(
        "/v1/brands",
        headers=auth,
        json={"name": "Owner brand", "story": "", "voice": ""},
    ).json()
    product = client.post(
        "/v1/products",
        headers=auth,
        json={"brand_id": brand["id"], "name": "Owner product"},
    ).json()
    assert (
        client.put(
            f"/v1/brands/{brand['id']}",
            headers=creator_auth,
            json={"name": "Forbidden edit", "story": "", "voice": ""},
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/v1/products/{product['id']}",
            headers=creator_auth,
            json={"brand_id": brand["id"], "name": "Forbidden edit"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/knowledge",
            headers=creator_auth,
            json={
                "title": "Creator contribution",
                "kind": "other",
                "content": "Creators may contribute knowledge for review.",
            },
        ).status_code
        == 201
    )


def test_owner_can_change_role_and_old_token_is_revoked(client, auth):
    _, accepted = invite_and_accept(
        client, auth, "reviewer@example.com", "reviewer", "reviewer-password", "Reviewer"
    )
    member = next(
        item
        for item in client.get("/v1/members", headers=auth).json()
        if item["email"] == "reviewer@example.com"
    )
    login = client.post(
        "/v1/auth/login",
        json={
            "organization_slug": "green-farm",
            "email": "reviewer@example.com",
            "password": "reviewer-password",
        },
    ).json()
    old_auth = {"Authorization": f"Bearer {login['access_token']}"}

    changed = client.patch(
        f"/v1/members/{member['membership_id']}",
        headers=auth,
        json={"role": "viewer"},
    )
    assert changed.status_code == 200
    assert changed.json()["role"] == "viewer"
    assert client.get("/v1/brands", headers=old_auth).status_code == 401

    new_login = client.post(
        "/v1/auth/login",
        json={
            "organization_slug": "green-farm",
            "email": "reviewer@example.com",
            "password": "reviewer-password",
        },
    )
    assert new_login.status_code == 200
    new_auth = {"Authorization": f"Bearer {new_login.json()['access_token']}"}
    assert client.get("/v1/brands", headers=new_auth).status_code == 200


@pytest.mark.parametrize("role", ["creator", "reviewer", "viewer"])
def test_non_asset_roles_cannot_edit_brand_or_product(client, auth, role):
    brand = client.post(
        "/v1/brands",
        headers=auth,
        json={"name": "Protected brand", "story": "", "voice": ""},
    ).json()
    product = client.post(
        "/v1/products",
        headers=auth,
        json={"brand_id": brand["id"], "name": "Protected product"},
    ).json()
    email = f"{role}@example.com"
    password = f"{role}-password"
    invite_and_accept(client, auth, email, role, password, role.title())
    login = client.post(
        "/v1/auth/login",
        json={
            "organization_slug": "green-farm",
            "email": email,
            "password": password,
        },
    ).json()
    member_auth = {"Authorization": f"Bearer {login['access_token']}"}

    assert (
        client.put(
            f"/v1/brands/{brand['id']}",
            headers=member_auth,
            json={"name": "Forbidden edit", "story": "", "voice": ""},
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/v1/products/{product['id']}",
            headers=member_auth,
            json={"brand_id": brand["id"], "name": "Forbidden edit"},
        ).status_code
        == 403
    )


def test_reviewer_cannot_edit_content_project(client, auth):
    brand = client.post(
        "/v1/brands",
        headers=auth,
        json={"name": "Project brand", "story": "", "voice": ""},
    ).json()
    product = client.post(
        "/v1/products",
        headers=auth,
        json={"brand_id": brand["id"], "name": "Project product"},
    ).json()
    project = client.post(
        "/v1/content-projects",
        headers=auth,
        json={
            "brand_id": brand["id"],
            "product_id": product["id"],
            "title": "Protected brief",
            "content_type": "social_post",
        },
    ).json()
    invite_and_accept(
        client,
        auth,
        "brief-reviewer@example.com",
        "reviewer",
        "reviewer-password",
        "Brief Reviewer",
    )
    login = client.post(
        "/v1/auth/login",
        json={
            "organization_slug": "green-farm",
            "email": "brief-reviewer@example.com",
            "password": "reviewer-password",
        },
    ).json()
    reviewer_auth = {"Authorization": f"Bearer {login['access_token']}"}
    assert (
        client.put(
            f"/v1/content-projects/{project['id']}",
            headers=reviewer_auth,
            json={
                "brand_id": brand["id"],
                "product_id": product["id"],
                "title": "Forbidden edit",
                "content_type": "social_post",
            },
        ).status_code
        == 403
    )


def test_member_management_is_tenant_scoped_and_owner_protected(client, auth):
    invite_and_accept(client, auth, "admin@example.com", "admin", "admin-password", "Admin")
    member = next(
        item
        for item in client.get("/v1/members", headers=auth).json()
        if item["email"] == "admin@example.com"
    )
    second = bootstrap(client, "membership-second", "second-owner@example.com")
    second_auth = {"Authorization": f"Bearer {second['access_token']}"}

    assert (
        client.patch(
            f"/v1/members/{member['membership_id']}",
            headers=second_auth,
            json={"role": "viewer"},
        ).status_code
        == 404
    )

    owner = next(
        item for item in client.get("/v1/members", headers=auth).json() if item["role"] == "owner"
    )
    assert (
        client.patch(
            f"/v1/members/{owner['membership_id']}",
            headers=auth,
            json={"role": "admin"},
        ).status_code
        == 409
    )

    admin_login = client.post(
        "/v1/auth/login",
        json={
            "organization_slug": "green-farm",
            "email": "admin@example.com",
            "password": "admin-password",
        },
    ).json()
    admin_auth = {"Authorization": f"Bearer {admin_login['access_token']}"}
    assert (
        client.post(
            "/v1/invitations",
            headers=admin_auth,
            json={
                "email": "new-owner@example.com",
                "role": "owner",
                "expires_in_hours": 72,
            },
        ).status_code
        == 403
    )


def test_invitation_is_single_use_and_token_is_only_stored_as_hash(client, auth, db):
    created = client.post(
        "/v1/invitations",
        headers=auth,
        json={"email": "Single.Use@Example.com", "role": "creator"},
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    invitation = db.scalar(
        select(OrganizationInvitation).where(OrganizationInvitation.id == payload["id"])
    )
    assert invitation is not None
    assert invitation.email == "single.use@example.com"
    assert invitation.token_hash != payload["token"]
    assert payload["token"] not in invitation.token_hash

    accepted = client.post(
        "/v1/invitations/accept",
        json={
            "token": payload["token"],
            "display_name": "Single Use",
            "password": "single-use-password",
        },
    )
    assert accepted.status_code == 200, accepted.text
    repeated = client.post(
        "/v1/invitations/accept",
        json={
            "token": payload["token"],
            "display_name": "Single Use",
            "password": "single-use-password",
        },
    )
    assert repeated.status_code == 409


def test_invitation_expiry_invalid_token_and_duplicate_active_invitation(client, auth, db):
    invalid = client.post(
        "/v1/invitations/inspect",
        json={"token": "not-a-real-invitation-token"},
    )
    assert invalid.status_code == 404

    first = client.post(
        "/v1/invitations",
        headers=auth,
        json={"email": "pending@example.com", "role": "reviewer"},
    )
    assert first.status_code == 201
    inspected = client.post(
        "/v1/invitations/inspect",
        json={"token": first.json()["token"]},
    )
    assert inspected.status_code == 200
    assert inspected.headers["cache-control"] == "no-store"
    duplicate = client.post(
        "/v1/invitations",
        headers=auth,
        json={"email": "PENDING@example.com", "role": "reviewer"},
    )
    assert duplicate.status_code == 409

    invitation = db.scalar(
        select(OrganizationInvitation).where(OrganizationInvitation.id == first.json()["id"])
    )
    invitation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    expired = client.post(
        "/v1/invitations/accept",
        json={
            "token": first.json()["token"],
            "display_name": "Expired",
            "password": "expired-password",
        },
    )
    assert expired.status_code == 410
    assert expired.headers["cache-control"] == "no-store"

    replacement = client.post(
        "/v1/invitations",
        headers=auth,
        json={"email": "pending@example.com", "role": "reviewer"},
    )
    assert replacement.status_code == 201, replacement.text


def test_existing_user_can_join_second_organization_with_current_password(client, auth):
    second = bootstrap(client, "second-team", "second-owner@example.com")
    second_auth = {"Authorization": f"Bearer {second['access_token']}"}
    invitation = client.post(
        "/v1/invitations",
        headers=second_auth,
        json={"email": "owner@green.example", "role": "viewer"},
    ).json()

    wrong_password = client.post(
        "/v1/invitations/accept",
        json={
            "token": invitation["token"],
            "display_name": "Existing Owner",
            "password": "wrong-password-value",
        },
    )
    assert wrong_password.status_code == 401
    accepted = client.post(
        "/v1/invitations/accept",
        json={
            "token": invitation["token"],
            "display_name": "Existing Owner",
            "password": "correct-horse-battery",
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["organization_id"] == second["organization_id"]


def test_invitation_requires_privileged_role_and_records_audit(client, auth, db):
    _, creator = invite_and_accept(
        client,
        auth,
        "invite-creator@example.com",
        "creator",
        "creator-password",
    )
    creator_auth = {"Authorization": f"Bearer {creator['access_token']}"}
    forbidden = client.post(
        "/v1/invitations",
        headers=creator_auth,
        json={"email": "forbidden@example.com", "role": "viewer"},
    )
    assert forbidden.status_code == 403

    created = client.post(
        "/v1/invitations",
        headers=auth,
        json={"email": "audited@example.com", "role": "viewer"},
    )
    accepted = client.post(
        "/v1/invitations/accept",
        json={
            "token": created.json()["token"],
            "display_name": "Audited",
            "password": "audited-password",
        },
    )
    assert accepted.status_code == 200
    events = db.scalars(
        select(AuditEvent).where(
            AuditEvent.action.in_(["invitation.created", "invitation.accepted"])
        )
    ).all()
    assert {event.action for event in events} == {
        "invitation.created",
        "invitation.accepted",
    }
    user = db.scalar(select(User).where(User.email == "audited@example.com"))
    assert user is not None
