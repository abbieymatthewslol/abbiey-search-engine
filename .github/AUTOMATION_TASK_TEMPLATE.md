# Automation Task Definition Template

Use this when triggering the maintainer agent manually or configuring a cron/webhook prompt.

## Copy/paste template

```md
Goal:
- <one clear outcome, e.g. "fix failing CI workflow on master">

Context:
- <links to PR/issue/run logs, if any>
- <what changed recently>

Scope:
- In scope: <files/systems allowed to change>
- Out of scope: <what must not be changed>

Definition of done:
- [ ] Code changes implemented
- [ ] Tests run (list exact commands + results)
- [ ] Docs updated if behavior/config changed
- [ ] Changes committed and pushed to the current feature branch

Constraints:
- Keep changes minimal and production-safe
- Do not rotate secrets or change infra unless explicitly requested
- If uncertain, prefer a small fix + clear notes over broad refactors
```

## Good prompt examples

### Example 1: Fix failing CI

```md
Goal:
- Fix the failing `python-package.yml` workflow on branch `master`.

Context:
- Failing run: <paste URL>
- Symptom: pytest fails in `tests/test_auth.py` after recent auth cleanup.

Scope:
- In scope: `app.py`, `tests/test_auth.py`, related helpers under `engine/`
- Out of scope: CSS/template redesign, dependency upgrades not required for the fix

Definition of done:
- [ ] Reproduce failure locally
- [ ] Implement targeted fix
- [ ] Run `pytest tests/ -v`
- [ ] Commit + push to the assigned branch
```

### Example 2: Hourly maintenance check

```md
Goal:
- Perform a lightweight repository health check and report actionable findings.

Scope:
- In scope: inspect git status, run focused tests, check recent CI failures
- Out of scope: speculative refactors when no issue is detected

Definition of done:
- [ ] Report any failing tests/workflows with file-level pointers
- [ ] If a clear low-risk fix exists, implement + commit + push it
- [ ] If no issues are found, explicitly state that
```

