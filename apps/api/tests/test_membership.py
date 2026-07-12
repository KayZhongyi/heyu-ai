from tests.conftest import bootstrap


def test_owner_can_add_member_and_role_is_enforced(client, auth):
    created = client.post(
        "/v1/members",
        headers=auth,
        json={
            "email": "creator@example.com",
            "display_name": "Content Creator",
            "password": "creator-password",
            "role": "creator",
        },
    )
    assert created.status_code == 201, created.text
    member = created.json()
    assert member["role"] == "creator"

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
    member = client.post(
        "/v1/members",
        headers=auth,
        json={
            "email": "reviewer@example.com",
            "display_name": "Reviewer",
            "password": "reviewer-password",
            "role": "reviewer",
        },
    ).json()
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


def test_member_management_is_tenant_scoped_and_owner_protected(client, auth):
    member = client.post(
        "/v1/members",
        headers=auth,
        json={
            "email": "admin@example.com",
            "display_name": "Admin",
            "password": "admin-password",
            "role": "admin",
        },
    ).json()
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
            "/v1/members",
            headers=admin_auth,
            json={
                "email": "new-owner@example.com",
                "display_name": "New Owner",
                "password": "new-owner-password",
                "role": "owner",
            },
        ).status_code
        == 403
    )
