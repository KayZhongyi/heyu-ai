# Exact-commit release evidence

Release claims must be tied to the exact Git commit that was tested. The
generator in `scripts/release-evidence.py` collects:

- the current commit, branch, repository, and worktree state;
- the successful GitHub Actions `CI` push run for that exact commit;
- the required job results for `api`, `browser-e2e`, `docker-build`,
  `repository-audit`, and `windows-package`;
- the locally collected Python test count;
- every current Alembic migration head.

## Generate a record

Install the project development dependencies, authenticate `gh`, and run from
the repository root:

```powershell
python scripts/release-evidence.py
```

The ignored output is written to:

```text
outputs/release-evidence/<full-commit-sha>.json
```

To verify a specific run or choose another ignored destination:

```powershell
python scripts/release-evidence.py `
  --run-id 29311635621 `
  --output outputs/release-evidence/manual-check.json
```

The command fails closed when:

- the worktree is dirty;
- no `CI` push run belongs to the exact commit;
- the workflow is incomplete or unsuccessful;
- a required job is absent, incomplete, or unsuccessful;
- the local test count or migration head cannot be established.

`--allow-dirty` is only for inspecting a work in progress. The resulting JSON
records `worktree_dirty: true` and must not be used as release sign-off.

## Boundary

This record proves automated evidence only. It deliberately reports human
acceptance as `not_verified`; a completed and retained human acceptance record
is still required by `docs/release-gates.md`.
