# Automation Task Template

Use this template when triggering cron/manual automation runs so the agent has a clear, actionable objective.

## Task Summary
- **Goal:** One sentence describing the desired outcome.
- **Why now:** Brief reason (incident, regression, maintenance, feature follow-up).

## Scope
- **In scope:** Exact files, systems, or workflows that may be changed.
- **Out of scope:** Explicit boundaries to avoid accidental broad edits.

## Acceptance Criteria
- [ ] Describe measurable result #1
- [ ] Describe measurable result #2
- [ ] Include how success is validated (tests/checks/manual verification)

## Constraints
- Branch requirements (if any)
- Performance/security constraints
- Dependency/version constraints

## Verification Steps
Provide commands the agent should run, for example:

```bash
pytest tests/ -v
python scripts/health_check.py
```

## Expected Deliverable
- Commit message convention (optional)
- Whether a PR should be opened
- Any release/deploy follow-up instructions

---

## Quick Example

**Goal:** Fix failing auth callback test in CI.

**In scope:** `app.py`, `tests/test_auth_callback.py`.

**Out of scope:** Frontend UI, unrelated auth providers.

**Acceptance criteria:**
- [ ] `tests/test_auth_callback.py` passes locally
- [ ] full test suite has no new failures
- [ ] behavior remains unchanged for existing valid callback payloads

**Verification:**

```bash
pytest tests/test_auth_callback.py -v
pytest tests/ -v
```
