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
3. Add source documents and mark reviewed sources as approved.
4. Create a structured content brief.
5. Generate a source-backed script through the AI gateway.
6. Edit the generated content into a new immutable version.
7. Submit a version for review and approve or reject it.
8. Inspect the audit trail and generation provenance.

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
- Unsupported performance predictions are excluded.
- Provider-specific AI behavior stays behind an internal gateway.
- Tenant isolation is tested as a security invariant.
