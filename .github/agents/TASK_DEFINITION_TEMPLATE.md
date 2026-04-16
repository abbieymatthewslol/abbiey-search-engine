# Agent Task Definition Template

Copy/paste this when opening an automation request so the task is actionable.

## 1) Problem Statement

Describe the bug/feature in 2-4 sentences:

- What is happening now?
- What should happen instead?
- Who is impacted?

## 2) Technical Scope

- Primary subsystem(s): (e.g. `app.py`, `engine/`, `templates/`, `static/`, `tests/`)
- Allowed changes:
- Out-of-scope changes:

## 3) Implementation Notes

- Existing behavior to preserve:
- Risky edge cases:
- Data or migration concerns:

## 4) Done Criteria

- [ ] Code changes are minimal and focused.
- [ ] Tests added/updated for changed behavior.
- [ ] Existing tests still pass.
- [ ] Docs/config updated if behavior or env requirements changed.

## 5) Verification Commands

List exact commands the agent should run, for example:

```bash
pytest tests/ -v
python app.py
```

## 6) Optional References

- Issue link:
- Prior PR:
- Logs/screenshots:

---

## Blank Prompt Fallback

If the request text is empty or vague (for example, "idk what to put here"), the agent should:

1. Confirm this template and `AUTOMATION_TASK_TEMPLATE.md` exist.
2. Make a low-risk docs-only improvement that reduces future prompt ambiguity.
3. Avoid speculative product changes without explicit requirements.
