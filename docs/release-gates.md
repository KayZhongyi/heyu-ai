# Release gates

No milestone is called "commercial-grade" solely because it has a polished UI.
Evidence must refer to the exact commit being evaluated.

## Current evidence status

The verified functional release-candidate baseline is:

- Commit: `5f8895a6eb95335b2d71f2dba42f61a8241417f1`
- GitHub Actions run: `29254510221`
- Result: `SUCCESS`
- Jobs: `api`, `repository-audit`, `browser-e2e`, `windows-package`, and
  `docker-build` all passed.
- Independent review: no P0 or P1 findings; engineering MVP candidate `GO`.

This evidence applies to that exact functional commit. Documentation changes
after it require their own exact-commit CI before the new repository HEAD is
treated as verified.

Local and remote evidence for the baseline:

- 59 Python tests passed with 97.09% coverage.
- Ruff lint and format checks passed.
- JavaScript syntax, i18n dictionary, content-renderer, and repository-audit
  checks passed.
- Playwright E2E passed for `zh-CN`, `zh-HK`, `en`, invitations, and
  390/700/1440-pixel layouts.
- The browser test binds the invalid-provider UI flow to the same HTTP request
  and verifies:
  - `POST /generate` returns `502`;
  - the persisted generation run is `failed`;
  - `output.error.code` is `provider_missing_citation`;
  - no completed run or content version is created;
  - the failed run is immediately visible and remains after reload;
  - locale changes preserve the selected project and rerender the failure
    state in all three locales;
  - the tested workspace phase emits no page error or unhandled rejection.
- Provider output validation fails closed when selected sources are not cited.
- Citation source IDs must belong to the server-selected context.
- Citation labels are rebuilt from server-trusted source metadata and duplicate
  source IDs are deterministically removed.
- The invalid-provider test double is isolated in `apps/api/e2e_app.py`; the
  production entry point remains `app.main:app`.
- SQLite migrations passed through `d8f4a1c2b3e6`.
- PostgreSQL was migrated from an empty database, restarted, backed up, and
  restored into a fresh volume.
- The PostgreSQL workflow created and accepted an invitation, then verified
  owner and invited-user access after restart and restore.

## Competition/local demo gate

- [x] Tenant-scoped workflow exists beyond the landing-page UI.
- [x] Zero-cost generation works without Ollama or Docker.
- [x] Brand, product, knowledge, and content facts require explicit review;
      editing an approved brand or product invalidates that approval.
- [x] Generation and versions retain provenance and history.
- [x] Publication, raw metrics, human diagnosis, improvement brief, and
      successor draft form a demonstrable loop.
- [x] Three locales and secure manual invitation flow are implemented.
- [x] Local automated and browser checks pass.
- [ ] A human completes the demo acceptance record using synthetic or
      explicitly authorized data.

**Decision:** conditional `GO` for a supervised local demonstration. This is
not approval to expose the service publicly.

## Engineering MVP gate

- [x] Authentication, tenant isolation, and RBAC are server-side.
- [x] Current schema has an Alembic migration chain.
- [x] No committed secret, private source material, database, or E2E output.
- [x] Deterministic and OpenAI-compatible provider boundaries are explicit.
- [x] Provider failures are persisted safely and never create content versions.
- [x] Provider output is schema-checked and citations are restricted to the
      exact selected context.
- [x] Browser E2E directly proves the provider-failure HTTP, persistence,
      no-version, reload, and trilingual UI path.
- [x] Limits avoid claims of semantic RAG, automatic video understanding,
      automatic publishing, or automatic analytics.
- [x] Browser E2E covers locale preservation, invitations, and layout.
- [x] Exact-commit CI passes `api`, `repository-audit`, `browser-e2e`,
      `windows-package`, and `docker-build`.
- [x] Empty PostgreSQL migration, restart persistence, and backup/restore pass.
- [x] An independent reviewer closed all P0/P1 findings.
- [ ] A human acceptance record is retained.

**Decision:** engineering implementation candidate `GO`; release sign-off
remains conditional on the retained human acceptance record.

## Public commercial operation gate

All engineering-MVP gates plus:

- [x] Invitation listing and explicit revocation
- [ ] Authentication/invitation rate limiting and abuse controls
- [ ] Approved email delivery and account recovery
- [ ] Production observability, alerting, incident ownership, and audit
      retention
- [ ] Rehearsed recovery with defined RPO/RTO
- [ ] Privacy, retention, deletion, and external-AI data-processing policies
- [ ] Security review of deployed topology and secret lifecycle
- [ ] Capacity/reliability targets tested against expected use

**Decision:** `NO-GO / STOP`.

## Anti-toy red lines

- UI-only access control
- Tenant queries without organization scoping
- Unversioned prompts or generated content
- Provider calls scattered through business endpoints
- Silent AI failures or fabricated citations
- Production dependence on seed/demo data
- Hard-coded credentials
- Marketing claims beyond implemented behavior

## Anti-overengineering red lines

- Microservices before independently scaled workloads exist
- A custom foundation model for the MVP
- A separate vector database before measured retrieval needs justify it
- Distributed events for synchronous CRUD
- Unsupported prediction metrics presented as capabilities
