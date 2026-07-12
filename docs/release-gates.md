# Release gates

No milestone is called “commercial-grade” solely because it has a polished UI.

## MVP release gate

- [x] Fresh clone starts with one documented Docker Compose command.
- [x] Database schema migration succeeds on an empty PostgreSQL database.
- [ ] Tests cover happy paths and cross-tenant denial for every tenant module.
- [x] Authentication and authorization are enforced server-side.
- [x] No committed secret or private business document.
- [x] AI generation works with the deterministic local provider.
- [x] Every generation exposes model, prompt, source, status, and timing data.
- [x] Only approved sources are eligible for production generation.
- [x] Content edits create versions instead of overwriting review history.
- [x] CI runs formatting/linting, tests, and migration validation.
- [x] Backup/restore and deployment instructions are documented.
- [ ] A human reviewer completes the end-to-end acceptance script.

Evidence and limits:

- Local Ruff, pytest, coverage, tenant-isolation tests, and isolated SQLite
  Alembic round trips have passed.
- GitHub Actions run `29198245091` passed for commit `62fd822`: API quality
  gates, the Windows user-facing installer/startup path and ZIP artifact, and
  the Docker Compose/PostgreSQL path all completed successfully.
- The Docker job built the image, started PostgreSQL and the API from a fresh
  checkout, applied Alembic migrations, bootstrapped a tenant, created a brand,
  restarted the API container, logged in again, and verified the persisted
  record.
- `docs/operations.md` and `docs/acceptance-test.md` define the remaining
  operator and human checks.
- PostgreSQL backup/restore and the complete human acceptance script remain
  open. CI currently proves restart persistence, not a full disaster-recovery
  drill.

## Anti-toy red lines

- UI-only access control
- shared tenant queries without organization scoping
- unversioned prompts or generated content
- AI calls embedded directly throughout business endpoints
- silent AI failures or fabricated citations
- production dependence on seed/demo data
- hard-coded credentials

## Anti-overengineering red lines

- microservices before an independently scaled workload exists
- a custom foundation model for the MVP
- a separate vector database before PostgreSQL search is measured insufficient
- distributed event infrastructure for synchronous CRUD workflows
- unsupported prediction metrics presented as product capabilities
