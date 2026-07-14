"""Validate the zero-cost Render demo blueprint without contacting Render."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "render.yaml"
DOCKERFILE = ROOT / "apps" / "api" / "Dockerfile"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    payload = yaml.safe_load(BLUEPRINT.read_text(encoding="utf-8"))
    services = payload.get("services", [])
    databases = payload.get("databases", [])

    require(len(services) == 1, "Blueprint must define exactly one web service.")
    require(len(databases) == 1, "Blueprint must define exactly one database.")

    service = services[0]
    database = databases[0]
    require(service.get("type") == "web", "Render service must be a web service.")
    require(
        service.get("runtime") == "docker", "Render service must use the tested image."
    )
    require(
        service.get("plan") == "free", "Demo web service must stay on the free plan."
    )
    require(
        service.get("healthCheckPath") == "/ready",
        "Health check must verify the database.",
    )
    require(
        service.get("autoDeployTrigger") == "checksPass",
        "Render must deploy only after GitHub checks pass.",
    )
    require(database.get("plan") == "free", "Demo database must stay on the free plan.")
    require(
        database.get("ipAllowList") == [],
        "Database must not allow public network access.",
    )
    require(
        service.get("region") == database.get("region"),
        "Web service and database must use the same region.",
    )

    env_vars = {item["key"]: item for item in service.get("envVars", [])}
    require(
        env_vars["APP_ENV"].get("value") == "production", "APP_ENV must be production."
    )
    require(
        env_vars["APP_SECRET"].get("generateValue") is True, "Secret must be generated."
    )
    require(
        env_vars["AUTO_CREATE_SCHEMA"].get("value") == "false",
        "Production must use Alembic rather than create_all.",
    )
    require(
        env_vars["ABUSE_LIMITS_ENABLED"].get("value") == "true",
        "Public demo abuse controls must stay enabled.",
    )
    require(
        env_vars["DEMO_ACCESS_PROTECTION_ENABLED"].get("value") == "true",
        "Public demo must require an outer access gate.",
    )
    require(
        env_vars["DEMO_BASIC_AUTH_USERNAME"].get("value") == "heyu-demo",
        "Public demo must use the documented access username.",
    )
    require(
        env_vars["DEMO_BASIC_AUTH_PASSWORD"].get("sync") is False,
        "Demo password must be supplied outside Git rather than committed.",
    )
    require(
        env_vars["AI_PROVIDER"].get("value") == "mock",
        "Free demo must not silently call a paid model provider.",
    )

    database_reference = env_vars["DATABASE_URL"].get("fromDatabase", {})
    require(
        database_reference.get("name") == database.get("name"),
        "DATABASE_URL must reference the Blueprint database.",
    )
    require(
        database_reference.get("property") == "connectionString",
        "DATABASE_URL must use Render's private connection string.",
    )

    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    require(
        "alembic upgrade head" in dockerfile, "Container must migrate before serving."
    )
    require("${PORT:-8000}" in dockerfile, "Container must honor Render's PORT.")

    print("Render Blueprint validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
