# Automation Task Template

Use this when configuring Cursor/GitHub automations so each run has a concrete, testable objective.

## Copy/Paste Template

```md
## Goal
<What outcome do you want? One sentence.>

## Why
<Why this run matters right now.>

## Scope
- In scope:
  - <file/path/system>
  - <file/path/system>
- Out of scope:
  - <anything this run should not touch>

## Constraints
- Keep changes small and safe.
- Do not change deployment settings unless explicitly requested.
- Do not add dependencies unless required.

## Acceptance Criteria
- [ ] <observable result #1>
- [ ] <observable result #2>
- [ ] Tests/checks run: <exact command(s)>

## Deliverable
<What should be committed or reported at the end>
```

## Good Example (Cron Maintenance)

```md
## Goal
Keep automation task-definition docs present and current.

## Why
Blank prompts (for example "idk what to put here") cause low-signal runs.

## Scope
- In scope:
  - AUTOMATION_TASK_TEMPLATE.md
  - .github/agents/TASK_DEFINITION_TEMPLATE.md
  - README.md (automation pointers)
  - .github/agents/my-agent.agent.md (blank-prompt fallback behavior)
- Out of scope:
  - Feature work unrelated to automation guidance

## Constraints
- Docs-only unless there is an obvious repo-health blocker.

## Acceptance Criteria
- [ ] Missing template docs are recreated.
- [ ] README links to automation templates.
- [ ] Agent file states what to do for blank/vague task text.
- [ ] `git status` shows only intended docs changes.

## Deliverable
A single commit with docs updates and a short summary.
```
