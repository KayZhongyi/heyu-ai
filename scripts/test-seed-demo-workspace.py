#!/usr/bin/env python3
"""Self-tests for the synthetic demo workspace seed workflow."""

from __future__ import annotations

import json

import seed_demo_workspace as module


class FakeClient:
    base_url = "https://demo.example"

    def __init__(self):
        self.brands = []
        self.products = []
        self.knowledge = []
        self.projects = []
        self.versions = {}
        self.calls = []
        self.next_id = 1

    def identifier(self, prefix):
        result = f"{prefix}-{self.next_id}"
        self.next_id += 1
        return result

    def request(self, method, path, *, payload=None, auth, token=None):
        self.calls.append((method, path, token))
        assert auth in {"basic", "bearer"}
        if path == "/v1/auth/login":
            return {"access_token": f"token-{payload['email']}"}
        if path == "/v1/brands" and method == "GET":
            return list(self.brands)
        if path == "/v1/brands" and method == "POST":
            item = {"id": self.identifier("brand"), "status": "draft", **payload}
            self.brands.append(item)
            return dict(item)
        if path == "/v1/products" and method == "GET":
            return list(self.products)
        if path == "/v1/products" and method == "POST":
            item = {"id": self.identifier("product"), "status": "draft", **payload}
            self.products.append(item)
            return dict(item)
        if path == "/v1/knowledge" and method == "GET":
            return list(self.knowledge)
        if path == "/v1/knowledge" and method == "POST":
            item = {"id": self.identifier("source"), "status": "draft", **payload}
            self.knowledge.append(item)
            return dict(item)
        if path == "/v1/content-projects" and method == "GET":
            return list(self.projects)
        if path == "/v1/content-projects" and method == "POST":
            item = {"id": self.identifier("project"), **payload}
            self.projects.append(item)
            self.versions[item["id"]] = []
            return dict(item)
        if path.endswith("/versions") and method == "GET":
            project_id = path.split("/")[3]
            return list(self.versions[project_id])
        if path.endswith("/generate") and method == "POST":
            project_id = path.split("/")[3]
            version = {
                "id": self.identifier("version"),
                "version_number": len(self.versions[project_id]) + 1,
                "status": "draft",
            }
            self.versions[project_id].append(version)
            return {"version": dict(version)}
        if path.endswith("/submit") and method == "POST":
            item = self.item_from_path(path)
            item["status"] = "pending_review"
            return dict(item)
        if path.endswith("/review") and method == "POST":
            item = self.item_from_path(path)
            item["status"] = payload["status"]
            return dict(item)
        raise AssertionError(f"Unexpected request: {method} {path}")

    def item_from_path(self, path):
        parts = path.split("/")
        if parts[2] == "brands":
            return next(item for item in self.brands if item["id"] == parts[3])
        if parts[2] == "products":
            return next(item for item in self.products if item["id"] == parts[3])
        if parts[2] == "knowledge":
            return next(item for item in self.knowledge if item["id"] == parts[3])
        if parts[2] == "content-projects":
            return next(
                item for item in self.versions[parts[3]] if item["id"] == parts[5]
            )
        raise AssertionError(path)


def seed(client):
    return module.seed_demo_content(
        client,
        organization_slug="heyu-demo",
        owner_email="leader@demo.example",
        owner_password="owner-password",
        creator_email="video@demo.example",
        creator_password="creator-password",
        reviewer_email="review@demo.example",
        reviewer_password="reviewer-password",
    )


client = FakeClient()
first = seed(client)
assert first["synthetic_data_only"] is True
assert first["brand"]["status"] == "approved"
assert first["product"]["status"] == "approved"
assert all(source["status"] == "approved" for source in first["knowledge"])
assert first["content_projects"][0]["latest_version_status"] == "approved"
assert first["content_projects"][1]["latest_version_status"] == "pending_review"
assert len(client.brands) == 1
assert len(client.products) == 1
assert len(client.knowledge) == 2
assert len(client.projects) == 2
assert sum(map(len, client.versions.values())) == 2

second = seed(client)
assert first == second
assert len(client.brands) == 1
assert len(client.products) == 1
assert len(client.knowledge) == 2
assert len(client.projects) == 2
assert sum(map(len, client.versions.values())) == 2

serialized = json.dumps(second)
for secret in (
    "owner-password",
    "creator-password",
    "reviewer-password",
    "token-leader",
    "token-video",
    "token-review",
):
    assert secret not in serialized

client.brands[0]["story"] = "Real customer data"
try:
    seed(client)
except RuntimeError as error:
    assert "not demo-owned" in str(error)
else:
    raise AssertionError("A same-name non-demo brand must not be overwritten")

client.brands[0]["story"] = module.SYNTHETIC_MARKER
client.versions[client.projects[0]["id"]][0]["status"] = "rejected"
try:
    seed(client)
except RuntimeError as error:
    assert "preserve the reviewer finding" in str(error)
else:
    raise AssertionError("A rejected latest version must not be replaced")

print("Synthetic demo workspace seed self-tests passed.")
