# Automation Task Template

Use this template whenever a cron/webhook automation is triggered.

## 1) Objective
- What should be accomplished in this run?
- Why this matters (bug risk, reliability, developer speed, etc.)

## 2) Scope
- In scope files/modules:
- Out of scope:

## 3) Required Deliverables
- [ ] Code/docs changes (if any)
- [ ] Validation steps and command output
- [ ] Commit(s) pushed to the automation branch
- [ ] PR opened/updated with a concise summary

## 4) Acceptance Criteria
- Clear, testable conditions that define done.
- Include exact behavior changes expected after completion.

## 5) Validation Commands
List exact commands the agent should run, for example:

```bash
git status --short --branch
python3 -m pytest tests/ -q
```

## 6) Context Links (Optional)
- Issue / PR:
- Incident / thread:
- Related docs:

## 7) Example Prompt
```text
Objective: Fix CSP regressions for inline scripts in auth templates.
Scope: app.py and templates/*.html only. No dependency upgrades.
Deliverables: apply fixes, run focused tests/manual checks, commit and push, open/update PR.
Acceptance criteria:
- All inline <script> tags in touched templates include nonce="{{ csp_nonce }}".
- CSP header still includes script-src nonce on each request.
- Auth pages load without CSP console errors.
Validation commands:
- rg "script-src" app.py
- rg "<script(?![^>]*nonce=)" templates -n
- python3 -m pytest tests/ -q --maxfail=1
```
