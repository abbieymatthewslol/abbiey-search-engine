# Automation Task Template

Use this template when triggering unattended jobs (cron/webhook/manual automation) so the agent gets a concrete, testable request.

## Copy/Paste Template

```md
## Goal
<one sentence: what should change?>

## Why
<brief reason, bug, or business need>

## Scope
- In scope:
  - <file/area/system 1>
  - <file/area/system 2>
- Out of scope:
  - <what should NOT be changed>

## Acceptance Criteria
- [ ] <observable result 1>
- [ ] <observable result 2>
- [ ] Tests or checks run: <exact command(s)>

## Constraints
- Branch: <branch-name>
- Keep changes: <small/safe/docs-only/etc.>
- Do not: <specific guardrails>

## Context (optional)
- Issue/PR: <URL>
- Logs/errors: <paste snippet>
- Related docs: <URL or file path>
```

## Good Prompt Examples

### Example 1: Docs-only maintenance

```md
## Goal
Improve README setup instructions so new contributors can run the app without guessing.

## Why
Recent onboarding feedback says setup order is unclear.

## Scope
- In scope:
  - README.md setup section
  - links to scripts in scripts/
- Out of scope:
  - code behavior changes

## Acceptance Criteria
- [ ] README has a clear first-run order
- [ ] Includes exact commands for Linux/macOS and Windows
- [ ] Run check: `python scripts/health_check.py`
```

### Example 2: Bug fix

```md
## Goal
Fix `/api/preview` timeout handling so failed fetches return JSON error payloads.

## Why
Frontend occasionally crashes when preview requests timeout.

## Scope
- In scope:
  - app.py preview route
  - related tests in tests/test_app.py
- Out of scope:
  - unrelated API routes

## Acceptance Criteria
- [ ] Timeout returns non-200 JSON with stable shape
- [ ] Existing tests pass and new timeout test added
- [ ] Run checks: `pytest tests/test_app.py -k preview -v`
```
