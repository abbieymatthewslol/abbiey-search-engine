# Task definition template for automations

Use one of these in `user_query` for scheduled runs.

## Hourly maintenance (recommended)

```text
Run hourly repo maintenance:
1) Check git status on the current branch.
2) Run python scripts/verify_production_env.py.
3) Run pytest tests/ -q --maxfail=1.
4) If everything passes, report "no action needed".
5) If a small, clear fix is needed, implement it, re-run relevant checks, then commit and push.
6) Summarize what ran, what passed/failed, and what changed.
```

## CI-focused sweep

```text
Review recent workflow failures, prioritize production-impacting issues, implement the smallest safe fix, run targeted tests, commit, and push.
```

## Docs-only cleanup

```text
Scan for stale setup/deploy docs and fix obvious mismatches with current scripts/workflows. Keep edits minimal, then commit and push.
```
