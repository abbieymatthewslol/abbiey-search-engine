# Task Definition Template for Automation Runs

Use this template when the trigger text is missing, vague, or too broad.

## Minimal actionable task

```md
Goal:
- <single concrete outcome>

Context:
- Why this matters: <brief reason>
- Relevant files: <paths>

Do:
1. <specific step>
2. <specific step>
3. <specific step>

Do not:
- <explicit guardrail>
- <explicit guardrail>

Definition of done:
- [ ] <verifiable requirement>
- [ ] <verifiable requirement>
- [ ] Checks run: <exact command>
```

## Fast fallback (blank prompt)

If the request is effectively "idk what to put here", use:

```md
Goal:
- Perform one low-risk maintenance improvement that prevents future vague automation prompts.

Context:
- Relevant files: `AUTOMATION_TASK_TEMPLATE.md`, `.github/agents/TASK_DEFINITION_TEMPLATE.md`, `.github/agents/my-agent.agent.md`, `README.md`

Do:
1. Ensure automation task templates exist and are up to date.
2. Ensure README points to the templates.
3. Ensure agent instructions define fallback behavior for blank/vague task text.

Do not:
- Change runtime application behavior.
- Modify deployment secrets or infra settings.

Definition of done:
- [ ] Changes are docs-only.
- [ ] Guidance includes at least one concrete example prompt.
- [ ] Branch is committed and pushed.
```
