#!/usr/bin/env python3
"""Create or verify a small role-based demo team through the public HTTP API.

Passwords are read from environment variables only. They are never accepted as
command-line arguments, written to the report, or printed to stdout.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ApiError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


class ApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        basic_username: str,
        basic_password: str,
        timeout: float = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.basic_username = basic_username
        self.basic_password = basic_password
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        auth: str,
        token: str | None = None,
    ) -> Any:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth == "basic":
            credential = f"{self.basic_username}:{self.basic_password}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(credential).decode(
                "ascii"
            )
        elif auth == "bearer":
            if not token:
                raise ValueError("Bearer authentication requires a token")
            headers["Authorization"] = f"Bearer {token}"
        else:
            raise ValueError(f"Unsupported authentication mode: {auth}")

        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raw = error.read()
            detail = error.reason
            if raw:
                try:
                    parsed = json.loads(raw)
                    detail = parsed.get("detail", detail)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass
            raise ApiError(error.code, str(detail)) from error
        except urllib.error.URLError as error:
            raise RuntimeError(
                f"Cannot reach {self.base_url}: {error.reason}"
            ) from error

        if not raw:
            return None
        return json.loads(raw)


@dataclass(frozen=True)
class DemoAccount:
    email: str
    display_name: str
    role: str
    password: str


@dataclass(frozen=True)
class DemoWorkspace:
    organization_name: str
    organization_slug: str
    owner: DemoAccount
    members: tuple[DemoAccount, ...]


def require_password(name: str, *, min_length: int = 10) -> str:
    value = os.environ.get(name, "")
    if len(value) < min_length:
        raise ValueError(
            f"{name} must be set and contain at least {min_length} characters"
        )
    return value


def validate_base_url(base_url: str, allow_http: bool) -> str:
    normalized = base_url.rstrip("/")
    parsed = urllib.parse.urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--base-url must be an absolute HTTP or HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("--base-url must not contain embedded credentials")
    is_local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not (allow_http or is_local):
        raise ValueError(
            "Remote demo setup requires HTTPS; use --allow-http only for testing"
        )
    if parsed.query or parsed.fragment:
        raise ValueError("--base-url must not contain a query string or fragment")
    return normalized


def bootstrap_or_login(
    client: ApiClient,
    workspace: DemoWorkspace,
) -> tuple[str, str, bool]:
    owner = workspace.owner
    try:
        result = client.request(
            "POST",
            "/v1/auth/bootstrap",
            payload={
                "organization_name": workspace.organization_name,
                "organization_slug": workspace.organization_slug,
                "email": owner.email,
                "display_name": owner.display_name,
                "password": owner.password,
            },
            auth="basic",
        )
        return result["access_token"], result["organization_id"], True
    except ApiError as error:
        if error.status != 409:
            raise

    result = client.request(
        "POST",
        "/v1/auth/login",
        payload={
            "organization_slug": workspace.organization_slug,
            "email": owner.email,
            "password": owner.password,
        },
        auth="basic",
    )
    return result["access_token"], result["organization_id"], False


def ensure_member(
    client: ApiClient,
    owner_token: str,
    workspace: DemoWorkspace,
    account: DemoAccount,
    *,
    repair_roles: bool,
) -> dict[str, Any]:
    members = client.request("GET", "/v1/members", auth="bearer", token=owner_token)
    existing = next(
        (
            member
            for member in members
            if member["email"].lower() == account.email.lower()
        ),
        None,
    )
    created = existing is None
    if existing is None:
        invitation = client.request(
            "POST",
            "/v1/invitations",
            payload={
                "email": account.email,
                "role": account.role,
                "expires_in_hours": 24,
            },
            auth="bearer",
            token=owner_token,
        )
        client.request(
            "POST",
            "/v1/invitations/accept",
            payload={
                "token": invitation["token"],
                "display_name": account.display_name,
                "password": account.password,
            },
            auth="basic",
        )
        members = client.request("GET", "/v1/members", auth="bearer", token=owner_token)
        existing = next(
            member
            for member in members
            if member["email"].lower() == account.email.lower()
        )
    elif existing["role"] != account.role:
        if not repair_roles:
            raise RuntimeError(
                f"{account.email} already has role {existing['role']}; "
                "review the account and rerun with --repair-roles if the change is intended"
            )
        existing = client.request(
            "PATCH",
            f"/v1/members/{existing['membership_id']}",
            payload={"role": account.role},
            auth="bearer",
            token=owner_token,
        )

    login = client.request(
        "POST",
        "/v1/auth/login",
        payload={
            "organization_slug": workspace.organization_slug,
            "email": account.email,
            "password": account.password,
        },
        auth="basic",
    )
    actor = client.request(
        "GET",
        "/v1/me",
        auth="bearer",
        token=login["access_token"],
    )
    if actor["role"] != account.role:
        raise RuntimeError(
            f"Role verification failed for {account.email}: "
            f"expected {account.role}, received {actor['role']}"
        )
    return {
        "email": account.email,
        "display_name": existing["display_name"],
        "role": actor["role"],
        "user_id": actor["user_id"],
        "created": created,
    }


def setup_demo_workspace(
    client: ApiClient,
    workspace: DemoWorkspace,
    *,
    repair_roles: bool = False,
) -> dict[str, Any]:
    owner_token, organization_id, owner_created = bootstrap_or_login(client, workspace)
    owner_actor = client.request("GET", "/v1/me", auth="bearer", token=owner_token)
    if owner_actor["role"] != "owner":
        raise RuntimeError("Configured owner account does not have the owner role")

    accounts = [
        {
            "email": workspace.owner.email,
            "display_name": workspace.owner.display_name,
            "role": "owner",
            "user_id": owner_actor["user_id"],
            "created": owner_created,
        }
    ]
    accounts.extend(
        ensure_member(
            client,
            owner_token,
            workspace,
            account,
            repair_roles=repair_roles,
        )
        for account in workspace.members
    )

    final_members = client.request(
        "GET",
        "/v1/members",
        auth="bearer",
        token=owner_token,
    )
    expected = {account["email"].lower(): account["role"] for account in accounts}
    actual = {member["email"].lower(): member["role"] for member in final_members}
    if any(actual.get(email) != role for email, role in expected.items()):
        raise RuntimeError(
            "Final member verification did not match the requested demo team"
        )

    return {
        "base_url": client.base_url,
        "organization_id": organization_id,
        "organization_name": workspace.organization_name,
        "organization_slug": workspace.organization_slug,
        "accounts": accounts,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or verify a two- or three-account Heyu AI demo team.",
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--accounts", type=int, choices=(2, 3), default=3)
    parser.add_argument("--organization-name", default="禾语 AI 演示空间")
    parser.add_argument("--organization-slug", default="heyu-demo")
    parser.add_argument("--owner-email", default="leader@demo.example")
    parser.add_argument("--creator-email", default="video@demo.example")
    parser.add_argument("--reviewer-email", default="review@demo.example")
    parser.add_argument(
        "--repair-roles",
        action="store_true",
        help="Change an existing demo member to the requested role.",
    )
    parser.add_argument("--allow-http", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        base_url = validate_base_url(args.base_url, args.allow_http)
        basic_password = require_password("HEYU_DEMO_PASSWORD", min_length=12)
        owner_password = require_password("HEYU_DEMO_OWNER_PASSWORD")
        creator_password = require_password("HEYU_DEMO_CREATOR_PASSWORD")
        reviewer_password = (
            require_password("HEYU_DEMO_REVIEWER_PASSWORD")
            if args.accounts == 3
            else None
        )
        passwords = [
            basic_password,
            owner_password,
            creator_password,
            *([reviewer_password] if reviewer_password else []),
        ]
        if len(passwords) != len(set(passwords)):
            raise ValueError("Demo access and account passwords must all be different")
        workspace = DemoWorkspace(
            organization_name=args.organization_name,
            organization_slug=args.organization_slug,
            owner=DemoAccount(
                email=args.owner_email,
                display_name="演示负责人",
                role="owner",
                password=owner_password,
            ),
            members=(
                DemoAccount(
                    email=args.creator_email,
                    display_name="内容创作",
                    role="creator",
                    password=creator_password,
                ),
                *(
                    (
                        DemoAccount(
                            email=args.reviewer_email,
                            display_name="内容审核",
                            role="reviewer",
                            password=reviewer_password,
                        ),
                    )
                    if args.accounts == 3
                    else ()
                ),
            ),
        )
        client = ApiClient(
            base_url,
            basic_username=os.environ.get("HEYU_DEMO_USERNAME", "heyu-demo"),
            basic_password=basic_password,
        )
        report = setup_demo_workspace(
            client,
            workspace,
            repair_roles=args.repair_roles,
        )
    except (ApiError, RuntimeError, ValueError) as error:
        print(f"Demo account setup failed: {error}", file=sys.stderr)
        return 1

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
