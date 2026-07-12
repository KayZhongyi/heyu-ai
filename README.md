# 禾语 AI · Heyu AI

禾语 AI is an open-source, multi-tenant AI workspace for agricultural brands and producer
organizations. The platform turns verified product knowledge into traceable
short-video and livestream scripts, while preserving human review, version
history, and auditability.

## MVP scope

- Multi-tenant organizations, memberships, and role-based access control
- Brand and agricultural product records
- Source-backed knowledge documents with review status
- Structured AI content briefs and script generation
- Immutable content versions and human approval workflow
- Provider-neutral AI gateway with a deterministic local development provider
- Docker-based local environment, automated tests, and CI

Not in the MVP: VR or medical features, autonomous digital-human livestreaming,
federated learning, blockchain/NFT features, or unsupported “viral prediction”.

## Repository layout

```text
apps/
  api/        FastAPI application and background-ready AI domain
  web/        Web workspace (added in the next milestone)
docs/
  architecture.md
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

Download the GitHub ZIP, extract it, and run the local start script that will be
included before the MVP release. Docker Compose remains available for a
production-like PostgreSQL environment, but it is not required for the basic
demo.

### Windows source package

The current source package can run without Docker. Python 3.12 is the only
prerequisite until the standalone Windows release is published.

1. Extract the repository to a drive with at least 2 GB free space.
2. Double-click `安装禾语AI.bat` once.
3. Double-click `启动禾语AI.bat`.
4. The browser opens the local API documentation automatically.

The installer creates `.venv`, `data`, and runtime files inside the extracted
project directory. It does not intentionally install project packages into the
system Python environment. Set `HEYU_PYTHON` to a Python 3.12 executable when
automatic Python discovery is not suitable.

The release gate for ordinary users is stricter: GitHub Releases will also
provide a standalone `HeyuAI-Windows-x64.zip` that bundles its runtime and does
not require Python, Node.js, or Docker.

## Docker quick start

Prerequisites: Docker with Compose.

```bash
cp .env.example .env
docker compose up --build
```

API documentation is then available at `http://localhost:8000/docs`.

For backend-only development, see [apps/api/README.md](apps/api/README.md).

## Security posture

- Every tenant-owned row carries an `organization_id`.
- Authorization is enforced in application services, not just the UI.
- AI outputs record provider, model, prompt version, source IDs, and latency.
- Source documents must be approved before production generation can cite them.
- The repository contains synthetic examples only; supplied business materials
  are not committed without explicit authorization.

## Status

The project is in active MVP development. See [docs/product.md](docs/product.md)
and [docs/release-gates.md](docs/release-gates.md) for acceptance criteria.

## License

Apache-2.0. See [LICENSE](LICENSE).
