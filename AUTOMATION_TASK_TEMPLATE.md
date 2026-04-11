# Automation Task Template

Use this template when configuring cron/webhook automation prompts so each run has a concrete, testable objective.

## Copy/paste prompt template

```md
## Goal
<One specific outcome. Example: "Harden `/api/preview` timeout handling.">

## Scope
- In scope:
  - <files/components allowed to change>
- Out of scope:
  - <explicit exclusions>

## Acceptance Criteria
1. <Behavioral requirement #1>
2. <Behavioral requirement #2>
3. <Tests or verification required>

## Constraints
- Branch: `<required branch name>`
- Keep changes: `<docs-only | code + tests>`
- Do not: <unsafe actions to avoid>

## Deliverables
- [ ] Code/docs changes committed and pushed
- [ ] Verification output included (tests/lint/commands)
- [ ] Short summary of what changed and why
```

## Good examples

- "Add rate-limit logging for `/api/chat` and include one unit test covering limit hits."
- "Update onboarding copy in `templates/welcome.html` and adjust related snapshot tests."
- "Investigate flaky test `tests/test_history_api.py::...`, fix root cause, and run the full history test file."

## Avoid prompts like

- "idk what to put here"
- "do something"
- "check repo"
- "fix stuff"

