# Automation Task Template

Use this template when creating a cron/webhook automation prompt for this repo.

## Copy/Paste Prompt

```
Goal:
<one sentence outcome>

Scope:
- Files or folders allowed to change:
- Files or folders that must not change:

Definition of done:
1. <expected behavior or output>
2. <required tests/verification>
3. <required docs updates, if any>

Constraints:
- Keep changes minimal and safe for production.
- Do not add secrets.
- Use existing project conventions from AGENTS.md and CLAUDE.md.
```

## Good Examples

1. **Stabilize flaky tests**
   - Goal: Make `tests/test_feedback_rerank.py` deterministic.
   - Definition of done: `pytest tests/test_feedback_rerank.py -v` passes consistently.

2. **Fix one UX bug**
   - Goal: Ensure the result preview panel closes when pressing `Escape`.
   - Scope: `static/script.js`, `tests/`.
   - Definition of done: behavior works and corresponding tests are updated.

3. **Docs-only maintenance**
   - Goal: Update Supabase setup steps in docs to match current scripts.
   - Scope: `README.md`, `CLAUDE.md`, `scripts/`.
   - Definition of done: instructions are accurate and internally consistent.

## When Prompt Is Blank or Vague

If the prompt is empty or says something like `idk what to put here`, default to:
1. Verify this file and `.github/agents/TASK_DEFINITION_TEMPLATE.md` exist.
2. Improve template examples/acceptance criteria wording if needed.
3. Keep the change docs-only unless there is an obvious low-risk blocker.
