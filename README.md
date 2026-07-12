# 禾语 AI · Heyu AI

禾语 AI is an open-source, multi-tenant AI workspace for agricultural brands and producer
organizations. The platform turns verified product knowledge into traceable
short-video and livestream scripts, while preserving human review, version
history, and auditability.

## MVP scope

- Multi-tenant organizations, memberships, and role-based access control
- Owner/Admin team management with immediate role-change enforcement
- Brand and agricultural product records
- Source-backed knowledge documents with review status
- Explicit draft → pending review → approved/rejected knowledge governance
- Immutable, linear knowledge revision chains with per-revision integrity metadata
- Browser-side UTF-8 TXT, Markdown, and CSV knowledge import with source
  filename, media type, and SHA-256 integrity metadata
- Structured AI content briefs and script generation
- Immutable content versions and human approval workflow
- Explicit draft → pending review → approved/rejected content governance
- Approved-content publication records and append-only performance snapshots
- Append-only, evidence-based structured video diagnosis reports
- Provider-neutral AI gateway with a deterministic local development provider
- Docker-based local environment, automated tests, and CI

Not in the MVP: VR or medical features, autonomous digital-human livestreaming,
federated learning, blockchain/NFT features, or unsupported “viral prediction”.

## Repository layout

```text
apps/
  api/        FastAPI application and background-ready AI domain
  web/        Browser workspace served by the API
docs/
  architecture.md
  acceptance-test.md
  operations.md
  product.md
  release-gates.md
scripts/
  setup-windows.ps1
  start-windows.ps1
安装禾语AI.bat
启动禾语AI.bat
```

## Zero-cost local demo

The demo is designed to run entirely on the user's computer:

- no domain name
- no cloud server
- no paid database
- no mandatory paid AI API
- SQLite and a deterministic local AI provider by default

Knowledge import currently accepts UTF-8 `.txt`, `.md`, `.markdown`, and
`.csv` files up to 1 MB. The browser reads the file locally and sends only the
editable extracted text plus source filename and media type to the API; the
original file is not stored. The API records a SHA-256 digest of the submitted
text so later changes can be detected. This digest proves content identity,
not factual truth, so human review remains required. PDF, DOCX, and PPTX
parsing are intentionally not included yet.

Download the GitHub ZIP, extract it, and run the included local start scripts.
Docker Compose remains available for a
production-like PostgreSQL environment, but it is not required for the basic
demo.

Every successful GitHub Actions run also publishes a
`heyu-ai-windows-source` artifact. It contains the same source-package layout
used by the automated Windows install-and-start verification.

### Windows source package

The current source package can run without Docker. Python 3.12 is the only
prerequisite until the standalone Windows release is published.

1. Extract the repository to a drive with at least 2 GB free space.
2. Double-click `安装禾语AI.bat` once.
3. Double-click `启动禾语AI.bat`.
4. The browser opens the local workspace at `http://127.0.0.1:8000/`.

Developer API documentation remains available at
`http://127.0.0.1:8000/docs`.

The installer creates `.venv`, `data`, and runtime files inside the extracted
project directory. It does not intentionally install project packages into the
system Python environment. Set `HEYU_PYTHON` to a Python 3.12 executable when
automatic Python discovery is not suitable.

The current ZIP workflow requires Python 3.12 for the one-time installation.
A future standalone Windows package may bundle the runtime, but it is not part
of the current verified release.

## Docker quick start

Prerequisites: Docker with Compose.

```bash
cp .env.example .env
docker compose up --build
```

The workspace is then available at `http://localhost:8000/`. Developer API
documentation is available at `http://localhost:8000/docs`.

For backend-only development, see [apps/api/README.md](apps/api/README.md).
For backups, upgrades, and recovery, see
[docs/operations.md](docs/operations.md). For manual release verification, see
[docs/acceptance-test.md](docs/acceptance-test.md).

## Security posture

- Every tenant-owned row carries an `organization_id`.
- Authorization is enforced in application services, not just the UI.
- AI outputs record provider, model, prompt version, source IDs, and latency.
- Source documents must be approved before production generation can cite them.
- Generation uses the latest approved revision in each knowledge chain. A rejected
  revision does not displace the preceding approved revision.
- A publication can reference only an approved content version. Operational
  metrics are stored as timestamped raw snapshots so later observations do not
  overwrite earlier evidence.
- Video diagnosis starts as a structured human-review record linked to a
  publication. Findings require a category, evidence, and an observation,
  opportunity, or risk label; the system does not invent an automatic score.
- The repository contains synthetic examples only; supplied business materials
  are not committed without explicit authorization.

## Status

The project is in active MVP development. See [docs/product.md](docs/product.md)
and [docs/release-gates.md](docs/release-gates.md) for acceptance criteria.

## License

Apache-2.0. See [LICENSE](LICENSE).
