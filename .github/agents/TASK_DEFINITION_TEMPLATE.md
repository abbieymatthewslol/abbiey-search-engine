# Task Definition Template (Detailed)

Use this when writing tasks for autonomous agent runs. The goal is to make tasks testable, bounded, and safe.

## Required fields

```md
### Task Summary
<One sentence with the exact intended outcome>

### Why this matters
<User or system impact in 1-3 bullets>

### Allowed Changes
- <file/module/path>
- <file/module/path>

### Forbidden Changes
- <explicitly prohibited area>

### Implementation Notes
- <important architecture constraints>
- <security/privacy constraints>

### Verification Steps
1. Run: <command>
2. Run: <command>
3. Manually confirm: <UI/API behavior>

### Acceptance Criteria
- [ ] <measurable criterion 1>
- [ ] <measurable criterion 2>
- [ ] <measurable criterion 3>
```

## Example: focused bug fix

```md
### Task Summary
Prevent duplicate analytics entries from making rerank tests flaky.

### Why this matters
- CI occasionally fails on deterministic assertions.
- Flakiness slows releases and hides real regressions.

### Allowed Changes
- `tests/test_feedback_rerank.py`
- related test fixture setup in `tests/conftest.py` if needed

### Forbidden Changes
- production ranking logic in `retrieval/` unless directly required by failing test root cause

### Implementation Notes
- Prefer isolated test data (unique query IDs) over global DB cleanup.
- Keep fix minimal and reproducible.

### Verification Steps
1. Run: `pytest tests/test_feedback_rerank.py -v`
2. Run the same command twice to verify repeatability.

### Acceptance Criteria
- [ ] Test passes on repeated local runs.
- [ ] No unrelated tests are modified.
- [ ] Root-cause note is captured in commit message.
```

## Example: docs-only fallback for undefined prompts

```md
### Task Summary
Improve automation prompt templates after receiving an undefined task body.

### Why this matters
- Undefined prompts lead to low-signal automation runs.
- Better templates improve task quality and reduce risky broad edits.

### Allowed Changes
- `AUTOMATION_TASK_TEMPLATE.md`
- `.github/agents/TASK_DEFINITION_TEMPLATE.md`
- `README.md` automation section
- `.github/agents/my-agent.agent.md` fallback instructions

### Forbidden Changes
- Application runtime code (`app.py`, `engine/`, `static/`) unless a critical blocker is discovered

### Implementation Notes
- Include at least two copy/paste examples with measurable acceptance criteria.
- Keep guidance specific to this repository structure.

### Verification Steps
1. Confirm all files above exist.
2. Confirm README points to both templates.
3. Confirm fallback behavior is explicit in agent instructions.

### Acceptance Criteria
- [ ] Templates are present and internally consistent.
- [ ] README links to templates.
- [ ] Fallback path for vague tasks is documented.
```

## Quality checklist before running automation

- Objective is singular and verifiable.
- Scope is explicit (what can and cannot change).
- Validation commands are included.
- Acceptance criteria can be checked without guesswork.
