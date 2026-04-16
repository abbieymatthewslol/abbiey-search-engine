# Task Definition Template (Agent-Focused)

Use this when assigning work to the maintainer agent.

## 1) Problem Statement
- What is broken or missing?
- Who is impacted?
- What user-visible behavior should change?

## 2) Technical Context
- Primary files:
  - `app.py`
  - `templates/...`
  - `static/script.js`
  - `tests/...`
- Constraints:
  - Keep changes minimal and production-safe.
  - Do not introduce secrets or new frameworks.

## 3) Exact Task
Describe the concrete edits expected. Be explicit about:
- Endpoints, templates, or scripts to touch
- Any migrations/config changes
- Backward compatibility expectations

## 4) Acceptance Criteria
- [ ] Behavior works as described
- [ ] Existing related behavior is not regressed
- [ ] Tests updated/added where appropriate
- [ ] `pytest tests/ -v` run (or skip reason documented)

## 5) Verification Steps
```bash
python app.py
pytest tests/ -v
```

## 6) Output Requirements
- Commit to the active task branch with descriptive commit messages.
- Summarize:
  - files changed,
  - tests run,
  - residual risks/follow-ups.

---

## Quick Prompt Starters

### Bug Fix
```md
Fix <bug> in <file/route>. Preserve existing behavior for <related feature>.
Add/adjust tests in <test file>. Verify with pytest.
```

### Small Feature
```md
Add <feature> to <route/template>. Keep UI consistent with existing styles.
Update docs and tests for the new behavior.
```

### Maintenance/Docs
```md
Improve <docs/config/script> for clarity and reliability without changing runtime behavior.
```

