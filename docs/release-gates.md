# Release gates

No milestone is called “commercial-grade” solely because it has a polished UI.

## MVP release gate

- [ ] Fresh clone starts with one documented Docker Compose command.
- [ ] Database schema migration succeeds on an empty PostgreSQL database.
- [ ] Tests cover happy paths and cross-tenant denial for every tenant module.
- [ ] Authentication and authorization are enforced server-side.
- [ ] No committed secret or private business document.
- [ ] AI generation works with the deterministic local provider.
- [ ] Every generation exposes model, prompt, source, status, and timing data.
- [ ] Only approved sources are eligible for production generation.
- [ ] Content edits create versions instead of overwriting review history.
- [ ] CI runs formatting/linting, tests, and migration validation.
- [ ] Backup/restore and production deployment instructions are documented.
- [ ] A human reviewer completes the end-to-end acceptance script.

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

