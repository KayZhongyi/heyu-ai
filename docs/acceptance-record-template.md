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
| Automated report | |
| GitHub Actions run | |

## Automated deployment report

| Field | Value |
| --- | --- |
| Report file | |
| Report status | PASS or FAIL |
| Base URL/profile | |
| Organization slug | |
| Passed steps | |
| Failed step or error | |

The report proves deployment and API workflow behavior only. It does not count
as a human visual or usability sign-off.

## Evidence checklist

| Area | Result | Evidence or finding |
| --- | --- | --- |
| Fresh installation and startup | | |
| Organization bootstrap and login | | |
| Team member creation and role management | | |
| Role change invalidates the member's old token | | |
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
| Automated Windows/SQLite acceptance report | | |
| Automated Docker/PostgreSQL acceptance report | | |

## Required screenshots

- [ ] Homepage Hero and primary entry point
- [ ] Homepage at mobile width
- [ ] Overview after login
- [ ] Owner/Admin team and permissions page
- [ ] Restricted member view without team-management entry
- [ ] Brand and product records
- [ ] Knowledge source before and after review
- [ ] Short-video generation result and provenance
- [ ] Livestream generation result
- [ ] Version and review history
- [ ] Audit events
- [ ] Successful GitHub Actions run for the recorded commit

## Human-only review

| Area | Result | Evidence or finding |
| --- | --- | --- |
| Homepage hierarchy and image treatment | | |
| Motion quality and reduced-motion behavior | | |
| Desktop and mobile responsive layout | | |
| Chinese typography, line height, and readable helper text | | |
| Independent workspace routes and browser Back/Forward | | |
| Knowledge import and review usability | | |
| Human-readable content draft and JSON disclosure | | |
| Reviewer note workflow and error messages | | |
| No planned capability presented as already available | | |

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
