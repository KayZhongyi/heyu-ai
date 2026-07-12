# MVP product specification

Product name: **禾语 AI / Heyu AI**

Positioning: an agricultural content and operations workspace that helps good
products communicate clearly, accurately, and consistently.

## Primary users

1. Organization owner: manages membership, brands, and billing boundaries.
2. Product manager: maintains verified product facts and source documents.
3. Content creator: creates briefs, generates scripts, and edits drafts.
4. Reviewer: approves knowledge and content versions.
5. Viewer: read-only access to approved assets.

## First complete workflow

1. Create an organization and first owner.
2. Add a brand and an agricultural product.
3. Add source documents, submit them for review, and approve verified sources.
4. Create a structured content brief.
5. Generate a source-backed script through the AI gateway.
6. Edit the generated content into a new immutable version.
7. Explicitly submit a draft version for review.
8. Approve or reject only a version currently pending review.
9. Inspect the audit trail and generation provenance.
10. Register an approved version as published and append timestamped performance
    snapshots as real platform data becomes available.

## Content types in the first release

- 30-second short-video script
- 60-second short-video script
- Livestream opening
- Single-product livestream pitch
- Audience-interaction prompts
- Comment replies
- Social post
- Titles and cover copy

The local deterministic provider returns a structure appropriate to each
content type rather than relabeling one generic script: timed shot lists for
short video, run-of-show segments for livestreams, and dedicated fields for
comment replies, social posts, titles, and cover copy. Every format retains the
same approved-source citations and prohibited-claim warnings.

## Product principles

- MVP means minimum scope, not disposable engineering.
- Human approval remains authoritative.
- Generated claims must be grounded in approved sources.
- Knowledge review follows the same explicit governance pattern as content:
  `draft` → `pending_review` → `approved` or `rejected`. Only approved sources
  enter AI context, and completed decisions cannot be silently overwritten.
- Reviewed knowledge is corrected by creating a new draft revision, never by
  overwriting the reviewed record. Each linear revision chain retains its group
  ID, parent revision, revision number, change summary, and independent SHA-256
  digest. Generation selects the latest approved revision in the chain; a
  rejected revision leaves the previous approved revision active.
- Text knowledge can be entered manually or imported from a local UTF-8 TXT,
  Markdown, or CSV file up to 1 MB. The original file is not persisted; the
  submitted text, source filename, media type, and SHA-256 digest are retained.
- A SHA-256 digest detects whether submitted source text changed. It does not
  validate factual accuracy, replace provenance review, or grant approval.
- PDF, DOCX, and PPTX extraction are outside the current MVP and must not be
  presented as supported import formats.
- Unsupported performance predictions are excluded.
- Provider-specific AI behavior stays behind an internal gateway.
- Generation provenance remains queryable after reload, including normalized
  input, full output, provider/model, prompt version, latency, and resolved
  source titles and citation labels.
- Tenant isolation is tested as a security invariant.
- Content review follows an explicit state machine: `draft` →
  `pending_review` → `approved` or `rejected`. Drafts cannot be reviewed
  directly, and completed reviews cannot be silently overwritten.
- The first operations loop stores publication platform, time, external
  reference, and raw performance snapshots such as views, likes, comments,
  shares, saves, follower gains, orders, and revenue. It deliberately does not
  invent a cross-platform score or claim predictive performance.
- Video diagnosis is initially an evidence-led human workflow. Each immutable
  report is linked to a publication and stores observation time, summary,
  optional transcript excerpt, and structured findings with evidence and
  recommendations. Automated media extraction can be added later without
  changing the audit model.
