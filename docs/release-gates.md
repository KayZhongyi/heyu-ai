# Release gates

No milestone is called “commercial-grade” solely because it has a polished UI.
Evidence must refer to the exact commit being evaluated.

## Current evidence status

The verified release-candidate baseline is:

- Commit: `50ba2088a22491458ecefa46f219da7cfa822cca`
- GitHub Actions run: `29244970544`
- Result: `SUCCESS`
- Jobs: `api`, `repository-audit`, `browser-e2e`, `windows-package`, and
  `docker-build` all passed.

This evidence applies to that exact commit. Later commits require their own
checks; documentation-only changes do not retroactively change the verified
baseline.

Local and remote evidence for the baseline:

- 45 Python tests passed.
- Ruff lint and format checks passed.
- i18n dictionary and content-renderer checks passed.
- Playwright E2E passed for `zh-CN`, `zh-HK`, `en`, invitations, and
  390/700/1440-pixel layouts.
- SQLite Alembic upgrade/check/downgrade/upgrade passed through migration
  `c4e9a8b7d6f5`.
- PostgreSQL was migrated from an empty database, restarted, backed up, and
  restored into a fresh volume.
- The PostgreSQL workflow created and accepted an invitation, then verified
  both owner and invited-user access after restart and restore.

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

**Decision:** conditional GO for a supervised local demonstration. This is not
approval to expose the service publicly.

## Engineering MVP gate

- [x] Authentication, tenant isolation, and RBAC are server-side.
- [x] Current schema has an Alembic migration chain.
- [x] No committed secret, private source material, database, or E2E output.
- [x] Deterministic and OpenAI-compatible provider boundaries are explicit.
- [x] Limits avoid claims of semantic RAG, automatic video understanding,
      automatic publishing, or automatic analytics.
- [x] Browser E2E covers locale preservation, invitations, and layout.
- [x] Exact-commit CI passes `api`, `repository-audit`, `browser-e2e`,
      `windows-package`, and `docker-build`.
- [x] Empty PostgreSQL migration, restart persistence, and backup/restore pass
      with the invitation migration.
- [ ] A human acceptance record is retained.
- [ ] An independent reviewer closes all P0/P1 findings.

**Decision:** NO-GO until the unchecked evidence exists.

## Public commercial operation gate

All engineering-MVP gates plus:

- [ ] Invitation listing and explicit revocation
- [ ] Authentication/invitation rate limiting and abuse controls
- [ ] Approved email delivery and account recovery
- [ ] Production observability, alerting, incident ownership, and audit
      retention
- [ ] Rehearsed recovery with defined RPO/RTO
- [ ] Privacy, retention, deletion, and external-AI data-processing policies
- [ ] Security review of deployed topology and secret lifecycle
- [ ] Capacity/reliability targets tested against expected use

**Decision:** NO-GO / STOP.

## Anti-toy red lines

- UI-only access control
- tenant queries without organization scoping
- unversioned prompts or generated content
- provider calls scattered through business endpoints
- silent AI failures or fabricated citations
- production dependence on seed/demo data
- hard-coded credentials
- marketing claims beyond implemented behavior

## Anti-overengineering red lines

- microservices before independently scaled workloads exist
- a custom foundation model for the MVP
- a separate vector database before measured retrieval needs justify it
- distributed events for synchronous CRUD
- unsupported prediction metrics presented as capabilities
