# Automation Task Template

Use this template when configuring a cron/webhook/manual automation prompt.

## Goal
Describe exactly what should be done and where:
- subsystem or files to target
- what outcome is expected
- what must not change

## Scope
- In scope:
  - 
- Out of scope:
  - 

## Steps to perform
1. 
2. 
3. 

## Verification
- Commands to run:
  - `pytest tests/ -v`
  - `python app.py` (or other quick smoke checks)
- What should pass:
  - 

## Deliverables
- Files expected to change:
  - 
- Commit message guidance:
  - `fix(...)`, `docs(...)`, `chore(...)`, etc.

## Good prompt examples

### Example: dependency maintenance
Update Python dependencies to latest patch/minor versions in `requirements.txt`, fix any import/runtime regressions, run `pytest tests/ -v`, and commit with a `chore(deps): ...` message. Do not change app behavior beyond compatibility fixes.

### Example: flaky test triage
Identify and fix flaky tests in `tests/` only. Prefer deterministic fixtures over sleep/retry logic. Run `pytest tests/ -v` and include a short root-cause note in the commit message.

### Example: docs cleanup
Improve README and contributor docs for automation setup. Keep changes docs-only, no application code changes. Ensure links and file paths resolve in this repository.
