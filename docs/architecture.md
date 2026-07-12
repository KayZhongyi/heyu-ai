# Architecture

## Deployment profiles

- **Local demo:** SQLite, local files, deterministic mock AI. No paid service.
- **Local AI:** SQLite/PostgreSQL plus an optional local model runtime.
- **Team/production:** PostgreSQL, private object storage, job workers, and a
  configured AI provider.

The same application code supports all profiles. The free local profile is not
a separate throwaway demo.

## Shape

The MVP uses a modular monolith for transactional business logic and an
AI-provider boundary designed to move long-running work into workers without
rewriting domain services.

```mermaid
flowchart LR
  Web["Web workspace"] --> API["FastAPI API"]
  API --> Auth["Identity and RBAC"]
  API --> Domain["Brands, products, knowledge, content, operations"]
  Domain --> DB["PostgreSQL"]
  Domain --> Gateway["AI gateway"]
  Domain --> Diagnosis["Evidence-led video diagnosis"]
  Domain --> PublicationDetail["Publication operations detail"]
  Diagnosis --> Brief["Immutable improvement brief"]
  Brief --> Version["Explicit successor content draft"]
  Gateway --> Mock["Deterministic local provider"]
  Gateway --> Providers["Configured external providers"]
  Domain --> Audit["Audit and provenance records"]
  PublicationDetail --> DB
  Brief --> DB
  Version --> DB
```

## Tenant isolation

Tenant-owned tables include a non-null `organization_id`. Service methods
receive an authenticated actor and organization context, then scope every read
and mutation by both. Cross-tenant behavior has explicit negative tests.
PostgreSQL row-level security is planned as defense in depth before production.

## AI provenance

Each generation stores:

- provider and model
- prompt template name and version
- normalized input brief
- source document IDs
- raw structured output
- latency and status
- creator and organization

Content versions reference the generation that produced them but remain
editable through append-only successor versions.

## Evolution

The first extraction candidates are document ingestion/video processing workers
and model calls. They will use durable jobs and object storage when those
features enter scope. Premature service decomposition is intentionally avoided.
