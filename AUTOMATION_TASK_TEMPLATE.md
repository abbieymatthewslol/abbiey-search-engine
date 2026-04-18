# Automation Task Template

Use this template when creating cron/webhook-triggered runs so the agent always has a concrete goal.

## Copy/Paste Template

```md
## Task
<one clear objective>

## Why
<why this matters right now>

## Scope
- In scope:
  - <item>
- Out of scope:
  - <item>

## Constraints
- <technical/business constraints>
- <files/components that must not change>

## Acceptance Criteria
- [ ] <observable success condition>
- [ ] <observable success condition>

## Verification
- Commands:
  - `<command>`
  - `<command>`
- Manual checks:
  - <check>

## Deliverables
- <files or behaviors expected at completion>
```

## Minimal Example

```md
## Task
Harden the `/api/related` handler against empty query edge cases.

## Why
Blank queries currently return inconsistent status codes in production logs.

## Scope
- In scope:
  - `app.py` request validation for `/api/related`
  - update/add tests under `tests/`
- Out of scope:
  - frontend UI copy changes

## Constraints
- Keep response format backward compatible.
- Do not add new dependencies.

## Acceptance Criteria
- [ ] Empty and whitespace-only queries return a consistent 400 payload.
- [ ] Existing successful queries are unchanged.
- [ ] Tests cover the new validation path.

## Verification
- Commands:
  - `pytest tests/ -v`

## Deliverables
- Code + tests + short summary of behavior changes.
```
