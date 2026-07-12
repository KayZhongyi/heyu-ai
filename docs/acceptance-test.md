# MVP acceptance test

Use a fresh local database or isolated test organization. Record the date,
commit SHA, deployment profile, reviewer, and pass/fail evidence.

## 1. Startup

- [ ] Install from a fresh source ZIP or clone using the documented procedure.
- [ ] Open `/health` and confirm `{"status":"ok"}`.
- [ ] Open `/` and confirm the workspace loads without missing assets.
- [ ] Confirm no private PDF, PPT, database, `.env`, or API key is committed.

## 2. Organization and authentication

- [ ] Create the first organization and owner through local bootstrap.
- [ ] Log out and log in again with the created credentials.
- [ ] Confirm an unauthenticated request to a tenant endpoint is denied.
- [ ] Confirm a user from another organization cannot read or modify this
      organization's brands, products, knowledge, projects, or versions.

## 3. Brand and product assets

- [ ] Create a brand with story and voice guidance.
- [ ] Create a product with origin, specification, storage instructions,
      selling points, and prohibited claims.
- [ ] Reload the page and confirm both records persist.

## 4. Trusted knowledge

- [ ] Create one source and leave it pending.
- [ ] Confirm pending knowledge is not used by generation.
- [ ] Approve the source.
- [ ] Confirm its title, content, citation label, reviewer, and status remain
      visible and traceable.
- [ ] Reject a second source and confirm it is not eligible for generation.

## 5. AI content workflow

- [ ] Create a 30-second short-video project for the product.
- [ ] Generate a script with the deterministic local provider.
- [ ] Confirm the output is structured and cites only approved source IDs.
- [ ] Inspect the generation record and confirm provider, model, prompt
      version, normalized brief, status, latency, and source IDs are present.
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
- [ ] Approve one version and reject another with a reviewer note.
- [ ] Confirm the full version and review history remains available.
- [ ] Confirm audit events identify actor, organization, action, and target.

## 7. Recovery and release evidence

- [ ] Back up the database using `docs/operations.md`.
- [ ] Restore it into an isolated environment.
- [ ] Confirm the organization and generated content survive the restore.
- [ ] Run lint, formatting, tests, coverage threshold, migration checks, and
      secret/file audit.
- [ ] Confirm GitHub Actions passes for the exact release commit.
- [ ] Capture screenshots of overview, knowledge review, generation result,
      version review, and the successful CI run.

## Acceptance record

```text
Commit:
Date:
Reviewer:
Profile: Windows/SQLite | Docker/PostgreSQL
Result: PASS | FAIL
Open findings:
Evidence location:
```

A polished interface alone is not a pass. Any tenant-isolation failure,
untraceable generation, unapproved-source use, destructive version overwrite,
committed secret, or failed recovery drill blocks the release.
