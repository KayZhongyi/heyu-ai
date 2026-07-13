# 禾语 AI · Heyu AI

禾语 AI is an Apache-2.0-licensed, multi-tenant AI content and operations
workspace for agricultural brands and producer organizations. It turns reviewed
product knowledge into traceable short-video and livestream content while
preserving human review, version history, tenant isolation, and auditability.

The repository is currently **private during pre-release review**. It is
structured for a later public source release, but it must not be described as
already public or generally available.

## What the MVP does

- Multi-tenant organizations, membership, RBAC, and immediate role-change
  enforcement
- Expiring, single-use team invitation links; plaintext tokens are returned
  once and only SHA-256 hashes are stored
- Editable brand, product, and content-brief records with tenant-scoped audit
  events
- TXT, Markdown, and CSV knowledge import with source metadata and SHA-256
  content identity
- Explicit knowledge submission, review, rejection, and immutable revision
  chains
- Bounded `lexical-v1` context selection using only the latest approved
  knowledge revision
- Eight structured output types, including short-video, livestream, comments,
  social copy, titles, and cover copy
- Provider-neutral generation gateway with a zero-cost deterministic provider
  and an OpenAI-compatible provider boundary
- Generation provenance: provider, model, prompt version, selected sources,
  context hashes, output, timing, and status
- Immutable content versions and explicit human review
- Publication registration, append-only performance snapshots, evidence-led
  human video diagnosis, improvement briefs, and explicit successor drafts
- Simplified Chinese, Hong Kong Traditional Chinese, and English interface
  switching without rewriting user-entered business data
- Windows/SQLite local startup without Docker, plus optional
  Docker/PostgreSQL deployment
- Python, repository-audit, browser E2E, Windows-package, and PostgreSQL CI jobs

Not in the MVP: VR, medical features, autonomous digital-human livestreaming,
federated learning, blockchain/NFT features, or unsupported “viral
prediction”.

## Honest capability boundaries

- `DeterministicProvider` is a zero-cost development provider, not a real
  language model.
- `lexical-v1` is deterministic lexical ranking, not semantic RAG or vector
  search.
- Video diagnosis is structured human input, not automatic video
  understanding.
- Publication is a registration record, not automatic posting to social
  platforms.
- Performance snapshots are manually entered, not automatically collected.
- The current system is an engineering-oriented MVP, not an approved
  internet-facing commercial service.

## Repository layout

```text
apps/
  api/                    FastAPI application and Alembic migrations
  web/                    Homepage and authenticated browser workspace
docs/
  acceptance-test.md      Manual acceptance record
  architecture.md         Boundaries and system shape
  operations.md           Startup, backup, restore, and testing
  product.md              Product behavior and scope
  release-gates.md        Demo, engineering MVP, and production gates
scripts/
  acceptance-smoke.py
  audit-repository.py
  setup-windows.ps1
  start-windows.ps1
  test-browser-e2e.js
  test-content-renderer.js
  test-i18n.js
安装禾语AI.bat
启动禾语AI.bat
```

## Zero-cost Windows demo

Prerequisite: Python 3.12. Docker, Node.js, a domain, Ollama, and a paid model
API are not required for ordinary use.

1. Extract the repository or Windows source artifact to a drive with at least
   2 GB free space.
2. Double-click `安装禾语AI.bat` once.
3. Double-click `启动禾语AI.bat`.
4. Open `http://127.0.0.1:8000/`.

The installer keeps `.venv`, SQLite data, and runtime files inside the extracted
project directory. Set `HEYU_PYTHON` when automatic Python discovery is not
suitable.

Knowledge import currently accepts UTF-8 `.txt`, `.md`, `.markdown`, and `.csv`
files up to 1 MB. The browser reads the file locally and sends editable text,
filename, and media type. The original file is not stored. PDF, DOCX, and PPTX
parsing are intentionally outside the current MVP.

## Optional Docker/PostgreSQL start

```bash
cp .env.example .env
docker compose up --build
```

The homepage is at `http://localhost:8000/`, the workspace at
`http://localhost:8000/workspace/`, and API docs at
`http://localhost:8000/docs`.

`/health` reports process liveness. `/ready` also verifies database
connectivity. Production mode fails closed on a default/short secret, SQLite,
automatic schema creation, or non-explicit/non-HTTPS CORS origins.

## Language support

The homepage and workspace support:

- `zh-CN`: Simplified Chinese
- `zh-HK`: Hong Kong Traditional Chinese with locally reviewed terminology
- `en`: English

Interface labels, dynamic feedback, dates, and generated-content presentation
follow the selected locale. Organization names, brand and product facts,
knowledge, briefs, and other business records stay exactly as entered. Locale
switching never machine-translates or overwrites them.

## Team invitation boundary

Owners and admins can create a manually shareable invitation link for a
non-Owner role. The link contains a cryptographically random token. Only its
hash is stored; it expires and can be accepted once. Inspection and acceptance
use POST with `Cache-Control: no-store`, and the browser removes the fragment
from the address bar after reading it.

The current MVP does not send invitation emails, revoke invitations before
expiry, or provide public-network rate limiting. Do not expose the local demo
directly to the internet.

## Verification

```powershell
python -m ruff check apps scripts
python -m ruff format --check apps scripts
python -m pytest -q
node scripts/test-i18n.js
node scripts/test-content-renderer.js
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
pnpm test:e2e
python scripts/audit-repository.py
```

Run deployment smoke against a started instance:

```powershell
python scripts/acceptance-smoke.py `
  --base-url http://127.0.0.1:8000 `
  --output outputs/acceptance/local.json
```

Automated evidence does not replace human visual, wording, accessibility,
usability, and business acceptance. See
[docs/acceptance-test.md](docs/acceptance-test.md) and
[docs/release-gates.md](docs/release-gates.md).

## Security posture

- Tenant-owned rows carry `organization_id`; authorization is server-side.
- Only approved knowledge may enter generation context.
- Rejected revisions do not displace the preceding approved revision.
- Context is bounded and records source/excerpt hashes and truncation state.
- Publications reference approved content; later observations do not overwrite
  prior metrics, diagnoses, briefs, or versions.
- Supplied private business materials are not committed without explicit
  authorization.
- `.env`, tokens, API keys, databases, original private PDFs/PPTs, and E2E
  evidence must not be committed.

## Status and license

The supervised local demo is functional. Engineering-MVP and public-operation
approval depend on the exact gates in `docs/release-gates.md`.

Apache-2.0. See [LICENSE](LICENSE).
