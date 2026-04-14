# Automation Task Template

Use this file when an automation trigger needs a concrete request (for example, cron jobs, webhooks, or scheduled maintenance runs).

## Copy/Paste Prompt

```md
## Objective
<One sentence describing what must be delivered.>

## Why this matters
<User-visible impact, bug risk, or operational reason.>

## Scope
- In scope:
  - <files, modules, or areas that can be changed>
- Out of scope:
  - <what should not be changed>

## Acceptance criteria
- [ ] <behavioral requirement 1>
- [ ] <behavioral requirement 2>
- [ ] <tests/verification updated when relevant>

## Validation
- Run:
  - `<command 1>`
  - `<command 2>`
- Expected result:
  - <what should pass or what output should appear>

## Constraints
- <performance/security/privacy constraints>
- <dependency or API limitations>
```

## Good Prompt Example

```md
## Objective
Improve empty-result handling for `/api/related` so clients get a stable JSON shape.

## Why this matters
The UI occasionally crashes when `related` is missing for rare queries.

## Scope
- In scope:
  - `app.py` response handling for `/api/related`
  - `tests/test_related_api.py`
- Out of scope:
  - Frontend layout or unrelated API endpoints

## Acceptance criteria
- [ ] Endpoint always returns `{ "related": [] }` when there are no matches
- [ ] Existing behavior for non-empty related terms remains unchanged
- [ ] Tests cover both empty and non-empty responses

## Validation
- Run:
  - `pytest tests/test_related_api.py -v`
- Expected result:
  - All tests pass with assertions on response shape

## Constraints
- Preserve current status codes
- Do not add new dependencies
```

## Quality Bar

Before submitting an automation prompt, make sure it includes:

- A specific objective (not "fix stuff")
- Explicit scope boundaries
- Measurable acceptance criteria
- Concrete validation commands
- Relevant constraints (security, privacy, performance)
