# MVP product specification

Product name: **禾语 AI / Heyu AI**

Positioning: an agricultural content and operations workspace that helps real
products be described accurately, consistently, and with traceable evidence.

## Primary users

1. Organization Owner: controls membership and organization boundaries.
2. Admin: manages the team except for granting Owner.
3. Product Manager: maintains brand, product, and reviewed knowledge.
4. Creator: creates briefs, generates content, and prepares revisions.
5. Reviewer: makes explicit knowledge and content decisions.
6. Viewer: reads authorized records without write access.

## First complete workflow

1. Bootstrap an organization and first Owner.
2. Invite team members through expiring, single-use links.
3. Create and maintain a brand and agricultural product.
4. Enter or import knowledge, submit it, and approve verified sources.
5. Create and later correct a structured content brief.
6. Generate source-backed content through the provider gateway.
7. Edit the result into append-only versions.
8. Submit brand, product, knowledge, and content drafts for explicit approval
   or rejection.
9. Register an approved version as externally published.
10. Append observed performance snapshots.
11. Record an evidence-led human diagnosis.
12. Convert findings into an improvement brief.
13. Explicitly create a successor draft and return it to normal review.
14. Inspect the audit trail and provenance throughout.

## Content types

- 30-second short-video script
- 60-second short-video script
- Livestream opening
- Single-product livestream pitch
- Audience-interaction prompts
- Comment replies
- Social post
- Titles and cover copy

The deterministic provider returns format-specific structures rather than
renaming one generic script. The browser provides a human-readable preview and
zero-cost TXT/JSON export without discarding the underlying structured data.

## Language experience

The interface supports Simplified Chinese (`zh-CN`), Hong Kong Traditional
Chinese (`zh-HK`), and English (`en`). Hong Kong Traditional Chinese is an
explicit product locale, not an automatic character conversion; terms such as
儲存、連結、檔案、影片 and 團隊 are selected for a natural Hong Kong interface.

Locale switching changes UI copy, dynamic validation and feedback, dates, and
content presentation. It must never translate or overwrite organization names,
brands, product facts, knowledge, briefs, or other user-entered business data.

## Team onboarding

An Owner or Admin can invite Admin, Product Manager, Creator, Reviewer, or
Viewer. Admin cannot invite Owner. A high-entropy token is returned once; only
its SHA-256 hash, normalized email, role, expiry, and state are stored.
Existing users authenticate with their existing password. New users choose a
password during acceptance.

The local MVP exposes the link for manual sharing. Email delivery, invitation
revocation, and public-network rate limiting are not current capabilities.

## Product principles

- MVP means minimum scope, not disposable engineering.
- Human approval remains authoritative.
- Brand and product facts follow
  `draft → pending_review → approved/rejected`.
- Editing a brand or product clears its reviewer metadata and blocks new
  generation until it is approved again.
- Only approved knowledge can support generated claims.
- Knowledge follows `draft → pending_review → approved/rejected`.
- Reviewed knowledge is corrected through a new linear revision, never an
  overwrite or history fork.
- Content follows the same explicit review-state principle and append-only
  version history.
- A SHA-256 digest proves submitted-text identity, not factual truth.
- Provider behavior stays behind one internal boundary.
- Every generation preserves normalized input, output, provider/model, prompt
  version, source/context evidence, status, and latency.
- External-provider failures remain visible as durable generation records
  rather than disappearing as untraceable HTTP errors.
- Only output matching the requested content type and citing sources selected
  for that exact run can become a content version.
- Context selection is bounded before any provider call.
- Tenant isolation is a tested security invariant.
- Metrics remain raw timestamped observations; no invented cross-platform
  score or viral prediction is shown.
- Diagnosis is immutable evidence-led human review.
- No diagnosis automatically modifies approved or published content.

## Honest capability boundaries

- `DeterministicProvider` is not a real language model.
- `lexical-v1` is not semantic RAG or vector retrieval.
- Publication registration is not automatic social-platform publishing.
- Performance snapshots are not automatic analytics ingestion.
- Video diagnosis is not automatic video understanding.
- PDF, DOCX, and PPTX extraction are not supported by the current importer.
- The architecture anticipates commercial use, but the current release is not
  approved for unsupervised internet operation.

## Release levels

1. **Competition/local demo:** supervised local workflow with synthetic or
   explicitly authorized data and the zero-cost provider.
2. **Engineering MVP:** reproducible install, current migrations, green CI for
   the exact commit, documented limitations, recovery evidence, and human
   acceptance.
3. **Public commercial operation:** engineering MVP plus abuse controls,
   complete invitation/account lifecycle, production observability, privacy
   and retention policy, recovery objectives, security review, and an approved
   external-model data-processing arrangement.
