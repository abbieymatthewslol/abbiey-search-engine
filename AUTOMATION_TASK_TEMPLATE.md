# Automation Task Prompt Template

Use this template when creating or updating automation prompts (cron, webhook, or manual automation triggers).

## Goal
State exactly what outcome should be produced.

Example:
- "Run production-readiness checks and fix any failing tests."
- "Review open CI failures on `master` and patch the root cause."

## Scope
List what can be changed and what should be avoided.

Example:
- Allowed: `app.py`, `tests/`, workflow files.
- Avoid: secrets, infrastructure credentials, unrelated refactors.

## Success Criteria
Define what must be true before the run is complete.

Example:
- All relevant tests pass locally.
- Changes are committed and pushed to the automation branch.
- A concise summary is posted with file-level change notes.

## Optional Constraints
- Time or cost constraints
- Style or architecture preferences
- Required checks (lint/test/security)

## Minimal Copy/Paste Prompt

```
Goal: <desired end state>
Scope: <allowed files/components>
Success Criteria:
- <criterion 1>
- <criterion 2>
Constraints: <optional>
```

If no task is known yet, write:

```
Goal: Improve automation reliability for undefined prompts.
Scope: Documentation only.
Success Criteria:
- Add or update automation prompt guidance docs.
- Link guidance from README.
```
