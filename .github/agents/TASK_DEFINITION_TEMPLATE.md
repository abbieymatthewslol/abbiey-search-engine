# Task Definition Template (Agent)

Use this when creating tasks for scheduled automations or background agent runs.

## Required Fields

- **Objective**: What should be true when the task is done?
- **Allowed scope**: Which files/subsystems may be edited?
- **Out of scope**: What must not be touched?
- **Verification**: Exact commands to run.
- **Acceptance criteria**: Concrete, user-visible outcomes.

## High-Quality Prompt Format

```md
Objective
<clear outcome in one sentence>

Context
<bug report, failing test, or reason this work matters>

Allowed scope
- <file/folder>
- <file/folder>

Out of scope
- <file/folder or behavior>

Implementation constraints
- Keep changes minimal and production-safe.
- Follow existing coding style and architecture.
- Do not add secrets or new infrastructure.

Verification
- <command 1>
- <command 2>

Acceptance criteria
1. <observable requirement>
2. <observable requirement>
3. <test or command output requirement>
```

## Example Prompt

```md
Objective
Fix search result keyboard navigation so j/k skips hidden cards.

Context
Users can focus hidden cards after filtering, which breaks preview navigation.

Allowed scope
- static/script.js
- tests/

Out of scope
- backend ranking logic
- template layout refactors

Implementation constraints
- Preserve existing shortcuts and ARIA labels.
- Add only targeted changes.

Verification
- pytest tests/ -k keyboard -v

Acceptance criteria
1. j/k focuses only visible result cards.
2. Preview panel updates for the focused visible card.
3. Existing keyboard-related tests pass.
```

## Fallback for Undefined Task Text

If task text is undefined (e.g., `idk what to put here`), run this default sequence:
1. Restore missing task templates (`AUTOMATION_TASK_TEMPLATE.md` and this file).
2. Improve examples or acceptance criteria wording.
3. Keep the change docs-only unless there is an obvious low-risk repository-health fix.
