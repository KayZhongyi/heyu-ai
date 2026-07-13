# Architecture

## Deployment profiles

- **Local demo:** SQLite plus the deterministic provider; no paid service.
- **External-model development:** SQLite/PostgreSQL plus an explicitly
  configured OpenAI-compatible API.
- **Team/production candidate:** PostgreSQL, production secrets, explicit HTTPS
  origins, durable backups, and an approved provider.

The same modular-monolith application supports all profiles. Ollama, Docker
Desktop, and a paid API are not prerequisites.

## System shape

```mermaid
flowchart LR
  Web["Homepage and workspace"] --> I18n["zh-CN / zh-HK / en dictionaries"]
  Web --> API["FastAPI API"]
  API --> Auth["Identity, membership, RBAC"]
  Auth --> Invite["Hashed, expiring, single-use invitations"]
  API --> Domain["Brands, products, knowledge, content, operations"]
  Domain --> DB["SQLite or PostgreSQL"]
  Domain --> Gateway["AI provider gateway"]
  Gateway --> Deterministic["DeterministicProvider"]
  Gateway --> External["Configured OpenAI-compatible provider"]
  Domain --> Audit["Audit and generation provenance"]
  Domain --> Publication["Publication and raw snapshots"]
  Publication --> Diagnosis["Human evidence-led diagnosis"]
  Diagnosis --> Brief["Immutable improvement brief"]
  Brief --> Version["Explicit successor draft"]
```

Long-running ingestion, media processing, and provider calls are future worker
candidates. Premature microservice decomposition is intentionally avoided.

## Tenant isolation

Tenant-owned tables include non-null `organization_id`. Authenticated service
operations scope reads and writes by actor and organization. Cross-tenant
negative tests cover domain modules. PostgreSQL row-level security remains a
future defense-in-depth option, not a claimed current control.

## AI provenance and retrieval

Each generation stores:

- provider and model
- prompt template and version
- normalized content brief
- source IDs and resolved citation labels
- raw structured output
- latency, status, creator, and organization

Before a provider call, `lexical-v1` selects a bounded context from the latest
approved revision in each eligible chain. Product scope is preferred; Chinese
character n-grams and Latin terms provide lightweight relevance ordering.
Hard source and character limits prevent unbounded prompts. The context
manifest stores source and excerpt hashes, included character counts, scope,
and truncation state.

The generation service also reloads the tenant-scoped brand and product and
requires both records to be `approved`. A material edit resets the affected
asset to `draft`, clears its prior reviewer metadata, and blocks subsequent
generation until another explicit review.

Provider success is not trusted at the HTTP boundary. The domain service
validates the returned object against the requested content type, requires
explicit `citations` and `risk_notes` arrays, and rejects every citation whose
`source_id` was not selected into that run's bounded context. Prompt
instructions are a generation aid, not a substitute for server-side
validation.

Provider timeouts, transport/HTTP failures, malformed responses, schema
failures, and unavailable citations are committed as
`GenerationRun(status=failed)` with a stable safe error code. Failed runs never
create a `ContentVersion`; raw provider responses, authorization headers, and
API keys are not persisted.

This is deliberately not called semantic RAG. PostgreSQL search or embeddings
can replace the policy later without changing provenance or provider
interfaces.

## Internationalization

The browser loads one i18n runtime and explicit dictionaries for `zh-CN`,
`zh-HK`, and `en`. Static HTML and dynamic application messages resolve through
the same translation keys. Locale state is browser-local and does not mutate
API records.

Business-data nodes are marked with `data-business-data` or
`data-i18n-ignore`; translation traversal must not alter them. Dictionary tests
check key parity and placeholders. Browser E2E verifies that unsaved form
values and saved brand data remain unchanged across locale switches.

## Secure invitation flow

```mermaid
sequenceDiagram
  participant Admin
  participant API
  participant DB
  participant Invitee

  Admin->>API: POST /v1/invitations
  API->>DB: Store token hash, email, role, expiry
  API-->>Admin: Return plaintext token once
  Admin-->>Invitee: Share /workspace/#invite=TOKEN
  Invitee->>Invitee: Read fragment and clear address bar
  Invitee->>API: POST /v1/invitations/inspect
  API-->>Invitee: Summary + Cache-Control no-store
  Invitee->>API: POST /v1/invitations/accept
  API->>DB: Lock, create membership, mark invitation used
  API-->>Invitee: Session + Cache-Control no-store
```

Fragments keep tokens out of ordinary request paths and server access logs, but
do not prevent browser extensions, screen capture, or recipient disclosure.
Tokens therefore remain expiring and single-use. A conditional uniqueness key
prevents duplicate active invitations for one organization and normalized
email.

## Verification architecture

- Python tests exercise domain behavior, state transitions, permissions, and
  tenant boundaries.
- SQLite Alembic round trips check current migrations in the API CI job.
- Playwright runs a real browser against a temporary API for localization,
  invitation handling, and responsive layout evidence.
- Windows CI installs and starts through the user-facing scripts.
- Docker CI applies migrations to empty PostgreSQL, exercises the deployment,
  restarts it, and performs backup/restore into a fresh volume.
- Repository audit rejects private documents, databases, secrets, and common
  credential patterns.
