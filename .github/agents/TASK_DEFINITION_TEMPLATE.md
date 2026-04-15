# Task Definition Template (for Agent Runs)

Use this template in manual runs, cron jobs, or webhook-triggered automations to give the agent enough context to execute without follow-up questions.

## Task Brief

### Objective
What should be accomplished?

### Why
Why is this needed now? (bug, regression, cleanup, reliability, etc.)

### Scope
Which files/components are in-scope and out-of-scope?

### Constraints
- Allowed/disallowed dependencies
- Performance or security constraints
- Branch/commit requirements

### Acceptance Criteria
- [ ] Behavior change is implemented
- [ ] Relevant tests are added or updated
- [ ] Validation commands pass
- [ ] Changes are committed and pushed

### Validation Commands
List exact commands the agent must run.

Example:
- `pytest tests/ -v`
- `python -m py_compile app.py`

### Deliverables
Specify expected output format.

Example:
- "Provide a concise summary + test evidence."

---

## Example: Bug Fix Prompt

```text
Objective:
Fix flaky assertions in feedback rerank tests.

Why:
CI intermittently fails when persisted analytics rows change ranking counts.

Scope:
Only modify tests under `tests/` and helper fixtures if needed.

Constraints:
- No production behavior changes.
- No new dependencies.

Acceptance Criteria:
- [ ] Flaky test is deterministic
- [ ] `pytest tests/test_feedback_rerank.py -v` passes

Validation Commands:
- pytest tests/test_feedback_rerank.py -v

Deliverables:
One commit with test-only changes and a short root-cause note.
```

---

## Example: Undefined Prompt Fallback

If a run is triggered with missing/vague input (for example "idk what to put here"), default to:

1. Verify task template docs still exist and are current:
   - `AUTOMATION_TASK_TEMPLATE.md`
   - `.github/agents/TASK_DEFINITION_TEMPLATE.md`
2. Verify README points to those templates.
3. Verify `.github/agents/my-agent.agent.md` contains fallback instructions.
4. Make docs-only repairs needed to prevent repeated blank prompts.
