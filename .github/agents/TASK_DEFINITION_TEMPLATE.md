# Task Definition Template for Agents

Use this when opening an automation job, requesting background fixes, or creating maintenance prompts.

## 1) Goal (required)
State the exact result you want.

Good:
- "Fix failing CI test `test_feedback_rerank.py` without changing ranking behavior."
- "Improve `/api/related` timeout handling and add regression tests."

Avoid:
- "make it better"
- "idk what to put here"

## 2) Allowed edits (required)
List files/directories the agent may modify.

Example:
- `app.py`
- `tests/test_related_api.py`
- `README.md`

## 3) Forbidden edits (required)
List boundaries clearly.

Example:
- No schema migrations
- No dependency upgrades
- No auth flow changes

## 4) Validation (required)
Include the commands that prove success.

Example:
- `pytest tests/test_related_api.py -v`
- `pytest tests/test_feedback_rerank.py -v`

## 5) Done definition (required)
Provide concrete acceptance checks.

Example:
- CI-targeted tests pass locally
- Existing behavior remains unchanged for non-timeout requests
- Changes are committed and pushed to the assigned branch

## 6) Context (optional but recommended)
- Links to issue/PR/logs
- Error snippets
- Known constraints or edge cases

---

## Copy/Paste Prompt Skeleton

Goal:
<required>

Allowed edits:
- <required>

Forbidden edits:
- <required>

Validation:
- <required command>

Done definition:
- <required acceptance item>

Context:
<optional>

---

## Fallback rule for blank prompts

If the incoming request is empty or placeholder text:
1. Recreate or improve this template and `AUTOMATION_TASK_TEMPLATE.md`.
2. Prefer docs-only changes unless there is an obvious low-risk repo-health break.
3. Do not make product behavior changes without a clearly defined task.
