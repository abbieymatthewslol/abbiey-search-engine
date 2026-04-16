# Automation Task Template

Use this template when defining work for scheduled/background agent runs.

```md
## Objective
One clear outcome the run should complete.

## Scope
- In scope:
  - ...
- Out of scope:
  - ...

## Context
- Relevant files/modules:
  - ...
- Relevant issue/PR links:
  - ...

## Required Changes
1. ...
2. ...

## Validation
- Commands to run:
  - `pytest tests/ -v`
  - ...
- Manual checks:
  - ...

## Deliverable
- Expected commit(s):
  - ...
- Definition of done:
  - ...
```

## Minimal Example

```md
## Objective
Fix flaky analytics test that fails when historical rows exist.

## Scope
- In scope: tests under `tests/test_feedback_rerank.py`
- Out of scope: production ranking logic changes

## Required Changes
1. Update tests to use unique per-run query strings.
2. Keep production code untouched unless strictly required for determinism.

## Validation
- Run: `pytest tests/test_feedback_rerank.py -v`

## Deliverable
- One commit on the current feature branch with passing targeted tests.
```

## If You Are Unsure What to Ask For

Start with:

```md
Objective: improve automation reliability for one concrete area.
Required changes: docs + tests only, no feature additions.
Validation: run the smallest relevant test command and report results.
```
