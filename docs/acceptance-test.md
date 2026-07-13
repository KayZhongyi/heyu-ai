# MVP acceptance test

Use a fresh local database or isolated test organization. Record the date,
commit SHA, deployment profile, reviewer, and pass/fail evidence.

## Automated deployment evidence

Run the deployment-level smoke test before the manual checklist:

```powershell
python scripts/acceptance-smoke.py `
  --base-url http://127.0.0.1:8000 `
  --output outputs/acceptance/local.json
```

The script uses only the Python standard library and creates randomly named
test organizations. It verifies the deployed homepage and workspace plus the
core API path from bootstrap through trusted knowledge, generation provenance,
human review, publication, append-only metrics, structured diagnosis,
improvement brief, successor draft, tenant isolation, and audit events.

A `PASS` report is deployment evidence, **not** a substitute for human visual,
responsive, wording, accessibility, or usability review. Keep the generated
JSON report with the release evidence. The `outputs/` directory is ignored by
Git.

## 1. Startup

- [ ] Install from a fresh source ZIP or clone using the documented procedure.
- [ ] Open `/health` and confirm `{"status":"ok"}`.
- [ ] Open `/` and confirm the product homepage loads without missing assets
      and contains no workspace forms or tenant data.
- [ ] Select **进入工作台** and confirm `/workspace/` opens the authentication
      or workspace surface.
- [ ] Open `/workspace/knowledge`, refresh the browser, then use Back/Forward
      and confirm the selected module remains independently addressable.
- [ ] Confirm no private PDF, PPT, database, `.env`, or API key is committed.

## 2. Organization and authentication

- [ ] Create the first organization and owner through local bootstrap.
- [ ] Log out and log in again with the created credentials.
- [ ] Confirm an unauthenticated request to a tenant endpoint is denied.
- [ ] Confirm a user from another organization cannot read or modify this
      organization's brands, products, knowledge, projects, or versions.

## 2A. Language experience

- [ ] Open the homepage and workspace in `zh-CN`, `zh-HK`, and `en`.
- [ ] Confirm addressable workspace modules remain usable in all three locales
      and no raw translation key is visible.
- [ ] Confirm Hong Kong Traditional Chinese uses reviewed local terminology
      rather than mechanical character conversion.
- [ ] Enter a mixed-language organization name, brand, product fact, and brief;
      switch through all locales and confirm every business value is unchanged.
- [ ] Save a brand, switch locale, reload, and confirm stored business data is
      unchanged.
- [ ] Confirm dynamic validation, success/error messages, review actions,
      invitations, operations, diagnoses, briefs, and successor drafts use the
      selected interface locale.

## 2B. Secure team invitations

- [ ] As Owner, create an expiring invitation for a non-Owner role and confirm
      the plaintext token appears only in the creation response/link.
- [ ] Confirm an Admin cannot invite an Owner.
- [ ] Open `/workspace/#invite=TOKEN` and confirm the fragment is promptly
      removed from the address bar.
- [ ] Confirm inspection and acceptance are POST requests and success/error
      responses include `Cache-Control: no-store`.
- [ ] Accept as a new user with a new password and confirm the assigned role.
- [ ] Invite an existing user and confirm acceptance requires the existing
      password.
- [ ] Confirm a second accept fails and concurrent acceptance cannot create
      duplicate membership.
- [ ] Confirm expired and duplicate-active invitations are rejected.
- [ ] List organization invitations and confirm no plaintext token, hash, or
      invitation link is returned.
- [ ] Revoke a pending invitation and confirm its original link immediately
      fails inspection/acceptance.
- [ ] Confirm a replacement invitation can be created for the same normalized
      email after revocation.
- [ ] Confirm Admin cannot revoke an Owner invitation.
- [ ] Confirm accepted, already revoked, and expired invitations cannot be
      revoked again.
- [ ] Confirm `invitation.created`, `invitation.accepted`, and
      `invitation.revoked` audit events without token or email leakage.
- [ ] Record that email delivery and internet-facing authentication/invitation
      rate limiting are not current capabilities.

## 3. Brand and product assets

- [ ] Create a brand with story and voice guidance.
- [ ] Create a product with origin, specification, storage instructions,
      selling points, and prohibited claims.
- [ ] Edit the brand and product, refresh the page, and confirm the updated values persist.
- [ ] Confirm the audit page contains `brand.updated` and `product.updated` events.
- [ ] Confirm creator, reviewer, and viewer roles cannot edit brand or product records.
- [ ] Reload the page and confirm both records persist.

## 4. Trusted knowledge

- [ ] Import a UTF-8 TXT or Markdown file no larger than 1 MB and confirm its
      text remains editable before saving.
- [ ] Confirm the saved source shows filename, media type, citation label, and
      the first characters of its SHA-256 digest.
- [ ] Confirm the original file is not stored by the application and that PDF,
      DOCX, and PPTX are not advertised as supported.
- [ ] Confirm changing the submitted text produces a different digest; treat
      the digest only as an integrity signal, not evidence that claims are true.
- [ ] Create one source and leave it pending.
- [ ] Confirm a draft source cannot be approved or rejected before submission.
- [ ] Submit the source and confirm its status becomes `pending_review`.
- [ ] Confirm pending knowledge is not used by generation.
- [ ] Approve the source.
- [ ] Confirm its title, content, citation label, reviewer, and status remain
      visible and traceable.
- [ ] Reject a second source and confirm it is not eligible for generation.
- [ ] Confirm an approved or rejected source cannot be reviewed again.
- [ ] Create a revision from a reviewed source and confirm the original record
      remains unchanged while the new record starts as `draft`.
- [ ] Confirm the revision retains the same source group ID, points to its parent,
      increments the revision number, records a change summary, and has its own
      SHA-256 digest.
- [ ] Confirm only the latest revision can be revised, preventing history forks.
- [ ] Approve a newer revision and confirm generation cites it instead of the
      older approved revision.
- [ ] Reject a newer revision and confirm the previous approved revision remains
      eligible for generation.

## 5. AI content workflow

- [ ] Create a brand and product and confirm both start as `draft`.
- [ ] Confirm generation is rejected while either asset is not approved.
- [ ] Submit and approve both assets through the workspace.
- [ ] Edit the approved product and confirm it returns to `draft`, its reviewer
      metadata is cleared, and generation is blocked again.
- [ ] Create a 30-second short-video project for the product.
- [ ] Edit its platform, audience, objective, or tone and confirm the revised brief
      is used only for future generation runs.
- [ ] Confirm existing generation output and content versions remain unchanged.
- [ ] Confirm `content_project.updated` appears in the audit trail and a reviewer
      cannot edit the brief.
- [ ] Generate a script with the deterministic local provider.
- [ ] Confirm the output is structured and cites only approved source IDs.
- [ ] Inspect the generation record and confirm provider, model, prompt
      version, normalized brief, status, latency, and source IDs are present.
- [ ] Confirm normalized input records `context_policy` and a context manifest
      with source/excerpt hashes, included character counts, scope, and
      truncation state.
- [ ] With more than four eligible knowledge chains or more than 12,000
      characters, confirm generation uses a bounded subset while retaining the
      latest approved revision rule.
- [ ] Reload the workspace, select the project again, and confirm its
      generation history still resolves source titles and citation labels.
- [ ] Repeat with at least one livestream content type.
- [ ] Confirm short video returns timed shots while livestream generation
      returns a run-of-show instead of a relabeled short-video template.
- [ ] Generate one comment reply, social post, or title-and-cover task and
      confirm the result uses fields appropriate to that content type.

## 6. Versions and review

- [ ] Create a successor content version without overwriting the AI draft.
- [ ] Confirm version numbers and change summaries are retained.
- [ ] Confirm a draft cannot be approved or rejected before it is explicitly
      submitted for review.
- [ ] Submit a draft and confirm its status becomes `pending_review`.
- [ ] Approve one version and reject another with a reviewer note.
- [ ] Confirm an approved or rejected version cannot be reviewed again.
- [ ] Confirm the full version and review history remains available.
- [ ] Confirm audit events identify actor, organization, action, and target.

## 7. Publication and operations loop

- [ ] Confirm a draft or pending content version cannot be recorded as
      published.
- [ ] Approve a content version and register its platform, publication time,
      optional external URL/content ID, and note.
- [ ] Add at least two timestamped performance snapshots and confirm the newer
      observation does not overwrite the older one.
- [ ] Open the publication detail endpoint and confirm it groups the publication,
      newest-first snapshots, and diagnosis history without a derived score.
- [ ] Confirm negative raw metrics are rejected.
- [ ] Confirm another organization cannot see the publication or its snapshots.
- [ ] Confirm publication and snapshot creation appear in the audit trail.
- [ ] Confirm the interface does not present an unvalidated viral score,
      prediction, or cross-platform comparison.

## 8. Structured video diagnosis

- [ ] Create a diagnosis for a publication with an observation time, summary,
      transcript excerpt, and at least one evidence-backed finding.
- [ ] Confirm findings accept only `observation`, `opportunity`, or `risk` and
      reject unsupported score labels.
- [ ] Add a follow-up diagnosis and confirm it does not overwrite the first.
- [ ] Confirm another organization cannot read the diagnosis history.
- [ ] Confirm diagnosis creation appears in the audit trail.
- [ ] Confirm the interface clearly presents diagnosis as evidence-led review,
      not an automated performance prediction.

## 9. Diagnosis-driven improvement workflow

- [ ] In the publication operations workspace, expand a diagnosis and create an
      improvement brief using its evidence, action, and guardrail fields.
- [ ] Confirm the new brief appears beneath the same publication without a page
      reload.
- [ ] Create an improvement brief from one diagnosis with evidence-backed
      actions and explicit guardrails.
- [ ] Create a second brief and confirm it does not overwrite the first.
- [ ] From the displayed brief, enter valid JSON content and explicitly create a
      successor content draft.
- [ ] Confirm invalid JSON is rejected in the interface before an API request is
      accepted.
- [ ] Open the content review workspace and continue the new draft through the
      normal submission and approval workflow.
- [ ] Confirm the draft links to the brief and the exact published source
      version while the approved source remains unchanged.
- [ ] Confirm another organization cannot read the briefs or create a draft.
- [ ] Confirm brief and successor-draft creation appear in the audit trail.

## 10. Recovery and release evidence

- [ ] Back up the database using `docs/operations.md`.
- [ ] Restore it into an isolated environment.
- [ ] Confirm the organization and generated content survive the restore.
- [ ] Run lint, formatting, tests, coverage threshold, migration checks, and
      secret/file audit.
- [ ] Confirm GitHub Actions passes for the exact release commit.
- [ ] Capture screenshots of overview, knowledge review, generation result,
      version review, and the successful CI run.
- [ ] Run `pnpm test:e2e` against the release build and retain screenshots plus
      `trace.zip`.
- [ ] Confirm 390px, 700px, and 1440px viewports have no horizontal overflow.
- [ ] Confirm the exact release commit has green `api`, `repository-audit`,
      `browser-e2e`, `windows-package`, and `docker-build` jobs.

## Acceptance record

```text
Commit:
Date:
Reviewer:
Profile: Windows/SQLite | Docker/PostgreSQL
Automated report:
Result: PASS | FAIL
Open findings:
Evidence location:
```

A polished interface alone is not a pass. Any tenant-isolation failure,
untraceable generation, unapproved-source use, destructive version overwrite,
committed secret, or failed recovery drill blocks the release.
