# MVP acceptance record

Copy this file for each release candidate. Do not replace checkboxes with
assumptions: attach a screenshot, command output, or a short finding for every
section.

## Release candidate

| Field | Value |
| --- | --- |
| Commit SHA | |
| Date and timezone | |
| Reviewer | |
| Profile | Windows/SQLite or Docker/PostgreSQL |
| Result | PASS or FAIL |
| Evidence folder | |

## Evidence checklist

| Area | Result | Evidence or finding |
| --- | --- | --- |
| Fresh installation and startup | | |
| Organization bootstrap and login | | |
| Tenant isolation | | |
| Brand and product records | | |
| Knowledge pending/approve/reject | | |
| 30-second short-video generation | | |
| Livestream generation | | |
| Generation provenance | | |
| Append-only content versions | | |
| Content approval and rejection | | |
| Audit trail | | |
| Backup and isolated restore | | |
| Exact-commit GitHub Actions run | | |
| Repository secret/private-file audit | | |

## Required screenshots

- [ ] Overview after login
- [ ] Brand and product records
- [ ] Knowledge source before and after review
- [ ] Short-video generation result and provenance
- [ ] Livestream generation result
- [ ] Version and review history
- [ ] Audit events
- [ ] Successful GitHub Actions run for the recorded commit

## Open findings

| Severity | Finding | Owner | Target date | Resolution evidence |
| --- | --- | --- | --- | --- |
| | | | | |

## Sign-off

```text
Reviewer:
Decision: PASS | FAIL
Reason:
Date:
```

A FAIL is mandatory for any tenant-isolation failure, unapproved-source use,
destructive version overwrite, missing generation provenance, committed secret,
failed recovery drill, or failed CI job.
