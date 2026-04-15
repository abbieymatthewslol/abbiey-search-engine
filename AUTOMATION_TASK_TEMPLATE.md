# Automation Task Template

Use this template when configuring cron, webhook, or manual automation prompts.

## Task
<one clear objective in one sentence>

## Why this run is needed
<business/user reason for doing this now>

## Scope
- In scope: <files, modules, or systems allowed to change>
- Out of scope: <areas that must not be touched>

## Acceptance criteria
- [ ] <observable outcome 1>
- [ ] <observable outcome 2>
- [ ] <tests/checks to run>

## Constraints
- Branch: `<branch-name>`
- Keep changes: `small` | `medium` | `large`
- Secrets/data rules: <any special handling notes>

## Optional context
- Related issue/PR: <url or id>
- Prior failures/logs: <key error snippet>

---

### Example

## Task
Fix flaky feedback rerank tests by preventing cross-run analytics state collisions.

## Why this run is needed
Scheduled maintenance runs should be deterministic; flaky tests block trusted automation.

## Scope
- In scope: `tests/test_feedback_rerank.py`
- Out of scope: ranking algorithm behavior in production code

## Acceptance criteria
- [ ] Test file uses unique per-run query identifiers
- [ ] `pytest tests/test_feedback_rerank.py -v` passes locally
- [ ] No product behavior changes outside tests

## Constraints
- Branch: `abbieymatthewslol/<automation-branch>`
- Keep changes: small
- Secrets/data rules: do not commit real credentials
