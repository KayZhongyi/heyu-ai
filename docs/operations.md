# Operations guide

This guide covers the zero-cost Windows/SQLite profile and optional
Docker/PostgreSQL profile. Keep backups outside the project directory where
possible.

## Local Windows profile

### Install and start

1. Install Python 3.12.
2. Run `安装禾语AI.bat` once.
3. Run `启动禾语AI.bat` whenever the workspace is needed.
4. Open `http://127.0.0.1:8000/`.

The installer creates `.venv` and runtime data inside the extracted repository.
It does not require Docker, Node.js, a domain, Ollama, or a paid AI provider.

### Interface language and business data

Use 简、繁、or EN on the homepage or workspace. The preference is stored in
the browser. Switching locale does not translate or rewrite business records.
If localized brand content is required, create and review it as an explicit
business asset rather than relying on the interface switch.

### Team invitations

An Owner or Admin opens the team module, enters an email, role, and expiry, then
copies the generated link. Share it through a trusted channel. The recipient
reviews the organization and role, then uses an existing password or chooses a
new-user password.

The plaintext token is shown once and never appears in the invitation history.
Owner and Admin can review organization-scoped invitation records in the team
module. A pending, unexpired invitation can be revoked there; its original link
becomes unusable immediately, and a replacement can then be created for the
same normalized email. Admin cannot create or revoke an Owner invitation.
Accepted, already revoked, and expired invitations cannot be revoked again.

There is no invitation email delivery or account-recovery workflow. The API
does apply database-backed limits to bootstrap, login, invitation creation,
token inspection, and acceptance, but this control alone is not approval to
expose the local demo directly to the internet.

### SQLite backup and restore

Stop the application before copying the configured SQLite database:

```powershell
New-Item -ItemType Directory -Force backups
Copy-Item apps\api\agri_content.db `
  "backups\agri-content-$(Get-Date -Format yyyyMMdd-HHmmss).db"
```

To restore, stop the application, preserve the current file, copy the selected
backup to the configured path, restart, and run the acceptance smoke. Never
merge SQLite files or restore a newer schema into older application code.

## Browser E2E verification

Node.js is not required for ordinary use. Maintainers run:

```powershell
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
$env:HEYU_BASE_URL = "http://127.0.0.1:8000"
pnpm test:e2e
```

Set `HEYU_BROWSER_PATH` to an existing Chromium-family executable to avoid a
browser download. Evidence is written under `outputs/browser-e2e` and ignored
by Git.

## Docker/PostgreSQL profile

Create `.env` from `.env.example`, replace production secrets, then run:

```bash
docker compose up --build
```

The API container runs `alembic upgrade head` before serving. PostgreSQL data
uses the named volume in `compose.yaml`.

### PostgreSQL backup and restore

```bash
docker compose exec -T db pg_dump -U agri -d agri -Fc > heyu.backup
docker compose exec -T db pg_restore \
  -U agri -d agri --clean --if-exists --no-owner --no-privileges \
  < heyu.backup
```

Production backups should be encrypted, stored outside the host, restored
regularly, and governed by explicit retention, RPO, and RTO.

## Upgrade and rollback

Upgrade:

1. Read release notes and back up the database.
2. Stop edits or schedule maintenance.
3. pull/extract the exact new version.
4. Rebuild dependencies or images.
5. Run `alembic upgrade head`.
6. Start and check `/health` plus `/ready`.
7. Run `docs/acceptance-test.md`.

Rollback application code and database separately. Prefer restoring the
pre-upgrade backup with its matching application version. Use `alembic
downgrade` only after reviewing data-loss consequences.

## Production configuration guardrails

Set `APP_ENV=production` only with:

- a unique `APP_SECRET` of at least 32 characters
- PostgreSQL `DATABASE_URL`
- `AUTO_CREATE_SCHEMA=false`
- `ABUSE_LIMITS_ENABLED=true`
- one or more explicit HTTPS `CORS_ORIGINS`

The application refuses production startup when these are absent.

Authentication and invitation limits are configured through the
`*_LIMIT_ATTEMPTS` and `*_LIMIT_WINDOW_SECONDS` values in `.env.example`.
Buckets are stored in PostgreSQL for production candidates and contain only
HMAC-protected subjects. Keep `APP_SECRET` stable across instances so all
workers derive the same subjects.

Do not trust caller-supplied forwarding headers by default. Set
`TRUSTED_PROXY_CIDRS` only to the exact address ranges of load balancers or
reverse proxies you operate. Direct clients and unlisted proxies are identified
from the TCP peer address; arbitrary `X-Forwarded-For` values are ignored.

## Secrets and providers

- Never commit `.env`, tokens, API keys, databases, or user/private source
  files.
- Run `python scripts/audit-repository.py` before release.
- ChatGPT/Codex subscriptions are not API credentials.
- Keep the deterministic provider as the no-cost fallback.
- Do not make paid calls without explicit authorization.
- Record provider, model, prompt version, sources, status, and latency for each
  external generation.

## Verification boundary

CI is configured for a clean Windows install, browser localization and
invitation handling, Docker image construction, empty PostgreSQL migration,
restart persistence, and backup/restore. Deployment jobs run
`scripts/acceptance-smoke.py`; browser CI uploads screenshots and a trace.

Only a green workflow for the exact release commit is valid evidence. Older
runs do not prove a newer or uncommitted worktree. A human must still complete
visual, wording, accessibility, usability, and business acceptance.
