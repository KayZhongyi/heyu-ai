#!/usr/bin/env python3
"""Self-tests for the secret-free demo account setup workflow."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).with_name("setup_demo_accounts.py")
SPEC = importlib.util.spec_from_file_location("setup_demo_accounts", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeClient:
    base_url = "https://demo.example"

    def __init__(self, *, existing=False):
        self.organization_id = "org-demo"
        self.owner_token = "owner-token"
        self.members = []
        self.invites = {}
        self.tokens = {}
        self.bootstrap_conflict = existing
        if existing:
            self.members.append(
                {
                    "membership_id": "membership-owner",
                    "user_id": "user-owner",
                    "email": "leader@demo.example",
                    "display_name": "演示负责人",
                    "role": "owner",
                }
            )
            self.tokens["leader@demo.example"] = "owner-token"

    def request(self, method, path, *, payload=None, auth, token=None):
        if path == "/v1/auth/bootstrap":
            assert auth == "basic"
            if self.bootstrap_conflict:
                raise MODULE.ApiError(409, "Organization slug already exists")
            self.bootstrap_conflict = True
            self.members.append(
                {
                    "membership_id": "membership-owner",
                    "user_id": "user-owner",
                    "email": payload["email"],
                    "display_name": payload["display_name"],
                    "role": "owner",
                }
            )
            self.tokens[payload["email"]] = self.owner_token
            return {
                "access_token": self.owner_token,
                "organization_id": self.organization_id,
                "user_id": "user-owner",
            }
        if path == "/v1/auth/login":
            assert auth == "basic"
            account_token = self.tokens.get(payload["email"])
            if not account_token:
                raise MODULE.ApiError(401, "Invalid credentials")
            member = next(
                item for item in self.members if item["email"] == payload["email"]
            )
            return {
                "access_token": account_token,
                "organization_id": self.organization_id,
                "user_id": member["user_id"],
            }
        if path == "/v1/me":
            member = next(
                item for item in self.members if self.tokens.get(item["email"]) == token
            )
            return {
                "user_id": member["user_id"],
                "organization_id": self.organization_id,
                "role": member["role"],
            }
        if path == "/v1/members" and method == "GET":
            assert auth == "bearer" and token == self.owner_token
            return list(self.members)
        if path == "/v1/invitations":
            assert auth == "bearer" and token == self.owner_token
            invitation_token = f"invite-{len(self.invites) + 1}"
            self.invites[invitation_token] = dict(payload)
            return {"token": invitation_token}
        if path == "/v1/invitations/accept":
            assert auth == "basic"
            invitation = self.invites[payload["token"]]
            index = len(self.members) + 1
            account_token = f"member-token-{index}"
            member = {
                "membership_id": f"membership-{index}",
                "user_id": f"user-{index}",
                "email": invitation["email"],
                "display_name": payload["display_name"],
                "role": invitation["role"],
            }
            self.members.append(member)
            self.tokens[member["email"]] = account_token
            return {
                "access_token": account_token,
                "organization_id": self.organization_id,
                "user_id": member["user_id"],
            }
        if path.startswith("/v1/members/") and method == "PATCH":
            membership_id = path.rsplit("/", 1)[-1]
            member = next(
                item for item in self.members if item["membership_id"] == membership_id
            )
            member["role"] = payload["role"]
            return dict(member)
        raise AssertionError(f"Unexpected request: {method} {path}")


def workspace():
    return MODULE.DemoWorkspace(
        organization_name="禾语 AI 演示空间",
        organization_slug="heyu-demo",
        owner=MODULE.DemoAccount(
            "leader@demo.example", "演示负责人", "owner", "owner-password"
        ),
        members=(
            MODULE.DemoAccount(
                "video@demo.example", "内容创作", "creator", "creator-password"
            ),
            MODULE.DemoAccount(
                "review@demo.example", "内容审核", "reviewer", "reviewer-password"
            ),
        ),
    )


def test_new_workspace():
    client = FakeClient()
    report = MODULE.setup_demo_workspace(client, workspace())
    assert report["organization_slug"] == "heyu-demo"
    assert [account["role"] for account in report["accounts"]] == [
        "owner",
        "creator",
        "reviewer",
    ]
    assert all(account["created"] for account in report["accounts"])
    serialized = MODULE.json.dumps(report)
    assert "owner-password" not in serialized
    assert "creator-password" not in serialized
    assert "reviewer-password" not in serialized
    assert "invite-" not in serialized


def test_existing_workspace_is_idempotent_and_repairs_role():
    client = FakeClient(existing=True)
    first = MODULE.setup_demo_workspace(client, workspace())
    creator = next(
        member for member in client.members if member["email"] == "video@demo.example"
    )
    creator["role"] = "viewer"
    try:
        MODULE.setup_demo_workspace(client, workspace())
    except RuntimeError as error:
        assert "--repair-roles" in str(error)
    else:
        raise AssertionError("Role mismatch should require explicit repair approval")
    second = MODULE.setup_demo_workspace(client, workspace(), repair_roles=True)
    assert first["accounts"][0]["created"] is False
    assert all(account["created"] is False for account in second["accounts"])
    assert creator["role"] == "creator"
    assert len(client.members) == 3


def test_remote_http_is_rejected():
    try:
        MODULE.validate_base_url("http://demo.example", allow_http=False)
    except ValueError as error:
        assert "requires HTTPS" in str(error)
    else:
        raise AssertionError("Remote HTTP should be rejected")
    assert MODULE.validate_base_url("http://127.0.0.1:8000", False).startswith(
        "http://"
    )
    try:
        MODULE.validate_base_url("https://user:secret@demo.example", allow_http=False)
    except ValueError as error:
        assert "embedded credentials" in str(error)
    else:
        raise AssertionError("Embedded URL credentials should be rejected")


def main():
    test_new_workspace()
    test_existing_workspace_is_idempotent_and_repairs_role()
    test_remote_http_is_rejected()
    print("Demo account setup self-tests passed.")


if __name__ == "__main__":
    main()
