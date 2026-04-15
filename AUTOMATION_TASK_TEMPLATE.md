# Automation Task Template

Use this template when defining a scheduled or event-driven automation task for this repository.

## 1) Goal
Describe the exact outcome you want.

Example:
- "Fix flaky tests in `tests/test_feedback_rerank.py`."
- "Audit auth templates for missing CSP nonces."

## 2) Scope
State what the agent is allowed to change.

Example:
- "Only docs and tests."
- "Backend Python only; no frontend/CSS changes."

## 3) Constraints
List hard rules that must be followed.

Example:
- "Do not add dependencies."
- "Do not change database schema."
- "Keep all changes on the current feature branch."

## 4) Validation
Specify commands the agent should run to prove the work.

Example:
- `pytest tests/test_feedback_rerank.py -v`
- `pytest tests/ -v`

## 5) Deliverable
Define what should be in the final result.

Example:
- "One commit with code + tests."
- "Summary including root cause and verification output."

---

## Copy/Paste Prompt

```text
Goal:
<what should be fixed or improved>

Scope:
<files/directories allowed>

Constraints:
- <rule 1>
- <rule 2>

Validation:
- <command 1>
- <command 2>

Deliverable:
<expected output and completion definition>
```

---

## If the Task Prompt Is Blank or Vague

If an automation run contains text like "idk what to put here", use a low-risk fallback:

1. Ensure this file exists and is accurate.
2. Ensure `.github/agents/TASK_DEFINITION_TEMPLATE.md` exists and is linked from README.
3. Ensure `.github/agents/my-agent.agent.md` includes explicit fallback behavior for blank prompts.
4. Keep changes docs-only unless there is an obvious repo-health blocker.
