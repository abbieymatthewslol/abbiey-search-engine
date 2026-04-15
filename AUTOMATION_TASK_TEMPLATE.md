# Automation Task Template

Use this template in automation `user_query` fields to make the task actionable.

```text
Goal: <what should be changed or verified>
Scope: <files/components to touch>
Acceptance criteria:
- <observable outcome 1>
- <observable outcome 2>
Validation:
- <exact command(s) to run>
Constraints:
- <anything to avoid, optional>
```

If you are unsure what to ask for, start with this safe default:

```text
Goal: Run test suite and fix any failing tests with minimal changes.
Scope: Only files needed to fix failures.
Acceptance criteria:
- `pytest tests/ -v` passes.
- Changes are limited to root cause fixes; no broad refactors.
Validation:
- pytest tests/ -v
Constraints:
- Do not add new dependencies unless required for a failing test fix.
```

For additional examples, see `.github/agents/TASK_DEFINITION_TEMPLATE.md`.
