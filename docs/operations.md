# Operations guide

This guide describes the current zero-cost local deployment and the
PostgreSQL-backed Docker profile. Keep backups outside the project directory
when possible.

## Local Windows profile

### Install and start

1. Install Python 3.12.
2. Run `瀹夎绂捐AI.bat` once.
3. Run `鍚姩绂捐AI.bat` whenever the workspace is needed.
4. Open `http://127.0.0.1:8000/`.

The installer creates `.venv` and runtime data inside the extracted repository.
It does not require Docker, Node.js, a domain, or a paid AI provider.

### SQLite backup

Stop the application before copying the database, so the backup represents one
consistent transaction boundary.

```powershell
New-Item -ItemType Directory -Force backups
Copy-Item apps\api\agri_content.db "backups\agri_content-$(Get-Date -Format yyyyMMdd-HHmmss).db"
```

If `DATABASE_URL` points to another SQLite path, back up that file instead.
Copy uploaded assets with the database when file uploads are enabled in a later
release.

### SQLite restore

1. Stop the application.
2. Preserve the current database under a different name.
3. Copy the selected backup to the configured SQLite database path.
4. Start the application and complete the acceptance smoke test.

Do not merge SQLite files or restore a database created by a newer schema into
older application code.

## Docker Compose profile

Create `.env` from `.env.example`, replace all production secrets, then run:

```bash
docker compose up --build
```

The API container runs `alembic upgrade head` before serving requests.
Application data is stored in the named PostgreSQL volume declared in
`compose.yaml`.

### PostgreSQL backup and restore

Use the actual Compose service name and credentials from `compose.yaml` and
`.env`.

```bash
docker compose exec -T db pg_dump -U agri -d agri -Fc > heyu.backup
docker compose exec -T db pg_restore -U agri -d agri --clean --if-exists --no-owner --no-privileges < heyu.backup
```

For a production deployment, store encrypted backups outside the host, test
restores regularly, and define retention and recovery-point objectives.

## Upgrade procedure

1. Read release notes and back up the database.
2. Stop content edits or schedule a maintenance window.
3. Pull or extract the new source version.
4. Rebuild dependencies or container images.
5. Run `alembic upgrade head`.
6. Start the service.
7. Check `/health` for process liveness and `/ready` for database readiness,
   then execute `docs/acceptance-test.md`.

## Production configuration guardrails

Set `APP_ENV=production` only with all of the following:

- a unique `APP_SECRET` containing at least 32 characters
- a PostgreSQL `DATABASE_URL`
- `AUTO_CREATE_SCHEMA=false` so Alembic remains the schema authority
- one or more explicit HTTPS origins in `CORS_ORIGINS`

The application refuses to start in production when these requirements are not
met. Development keeps the zero-cost SQLite defaults. Docker Compose also
checks `/ready`, which performs a database query rather than reporting only
that the web process is alive.

## Rollback

Application rollback and database rollback are separate decisions.

1. Stop writes and retain a fresh backup.
2. Prefer restoring the pre-upgrade backup with the matching application
   version.
3. Use `alembic downgrade` only after reviewing the target migration for data
   loss.
4. Start the previous application version and repeat acceptance checks.

## Secrets and external AI providers

- Never commit `.env`, tokens, API keys, production databases, or user files.
- Run `python scripts/audit-repository.py` before a release. CI runs the same
  tracked-file audit and fails on private documents, database files, private
  keys, environment files, and common credential formats. This is a release
  guardrail, not a replacement for credential rotation or a dedicated secret
  scanner.
- Use a long random `APP_SECRET` outside local demonstrations.
- Treat ChatGPT or Codex subscriptions as separate from API credentials.
- Keep the deterministic provider as the no-cost fallback.
- When an external provider is configured, record provider, model, prompt
  version, source IDs, status, and latency for every generation.

## Current verification boundary

The Windows/SQLite profile has been exercised locally. CI validates a clean
Windows install, Docker image construction, empty PostgreSQL migration,
container restart persistence, and backup restoration into a newly created
PostgreSQL volume. Both deployment jobs also run
`scripts/acceptance-smoke.py` and upload the resulting JSON report as a CI
artifact. A human still needs to complete the visual, responsive, wording, and
usability portions of `docs/acceptance-test.md` before a release is approved.
