# Task Definition Template for Automations

Use this file when filling the automation `user_query` field.

## Quick copy/paste template

```text
Goal: <one sentence outcome>

Scope:
- In scope: <files/components to touch>
- Out of scope: <what not to change>

Definition of done:
1) Implement the requested change.
2) Add or update tests for the behavior.
3) Run relevant checks and report results.
4) Commit and push to the current feature branch.

Constraints:
- Keep changes minimal and production-safe.
- Do not change unrelated files.
- Do not add secrets.
```

## Example: bug fix task

```text
Fix the login redirect loop when Supabase session restore fails.

Scope:
- In scope: app.py auth routes, templates/auth_confirm.html, auth-related tests.
- Out of scope: unrelated UI styling changes.

Definition of done:
1) Reproduce and fix the redirect loop.
2) Add regression tests.
3) Run `pytest tests/ -v` (or the relevant subset) and report output.
4) Commit and push changes to the active branch.
```

## Example: hourly cron default

```text
Perform a lightweight maintenance pass.

Steps:
1) Inspect repository status and recent workflow configuration changes.
2) If a clear, safe fix is needed (broken docs, small config typo, flaky assertion), implement it.
3) Run targeted tests for the touched area.
4) Commit and push if changes were made.
5) If no changes are needed, report "no action required" with brief reasoning.
```

## If you are unsure what to put

Use this single line:

```text
Perform a lightweight maintenance pass and make one safe, high-confidence improvement if needed; otherwise report no action required.
```
