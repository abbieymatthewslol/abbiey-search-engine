# Task Definition Template for Agent Runs

Use this template in issue descriptions, automation triggers, or manual agent prompts.

## 1) Objective

Describe the exact user-facing outcome in 1-2 sentences.

Example:
- "Fix the weather card so it renders a friendly empty state instead of a server error when Open-Meteo is unavailable."

## 2) Boundaries

- **Allowed files/areas:** `<paths>`
- **Do not change:** `<paths or systems>`
- **Non-goals:** `<explicitly excluded work>`

## 3) Acceptance Criteria

- [ ] Behavior is correct for happy-path and at least one edge case
- [ ] Tests added/updated where applicable
- [ ] Existing relevant tests pass
- [ ] Changes are committed and pushed to the current task branch

## 4) Verification

List exact commands the agent should run.

```bash
pytest tests/ -v
```

Add any manual verification steps if UI changes are involved.

## 5) Output Format

Ask for:
- concise summary
- files changed
- test results
- follow-up risks or TODOs

## Blank/Vague Prompt Fallback

If the prompt text is blank or vague (for example, "idk what to put here"), perform a low-risk maintenance task that improves future prompt quality:

1. Ensure these files exist and are current:
   - `AUTOMATION_TASK_TEMPLATE.md`
   - `.github/agents/TASK_DEFINITION_TEMPLATE.md`
2. Ensure `README.md` points users to those templates.
3. Ensure `.github/agents/my-agent.agent.md` instructs the agent to follow this fallback.
4. Prefer docs-only edits unless there is an obvious trivial blocker to repository health.
