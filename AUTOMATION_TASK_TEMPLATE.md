# Automation Task Template

Use this template when creating cron/webhook automation prompts for this repository.
Fill in every section so the agent can execute the task end-to-end without follow-up.

## Copy/Paste Prompt

```md
## Objective
<one clear outcome>

## Context
- Why this task matters:
- Relevant files/directories:
- Related issue/PR links (optional):

## Scope
- In scope:
- Out of scope:

## Required Changes
1. <specific change #1>
2. <specific change #2>

## Validation
- Commands to run:
  - `pytest tests/ -v`
  - <other required checks>
- Manual verification:
  - <observable behavior>

## Deliverables
- Expected files to change:
- Expected commit message style:

## Acceptance Criteria
- [ ] <criterion 1>
- [ ] <criterion 2>
- [ ] No regressions in existing behavior
```

## Prompt Quality Bar

Before saving an automation prompt, verify:

- It defines a concrete objective (not "idk what to put here").
- It names specific files or subsystems.
- It includes at least one validation command.
- Acceptance criteria are testable and user-visible.
- Scope clearly separates in-scope and out-of-scope work.

## Example (Docs Task)

```md
## Objective
Improve onboarding docs for local development.

## Context
- Why this task matters: New contributors miss setup prerequisites.
- Relevant files/directories: `README.md`, `CLAUDE.md`

## Scope
- In scope: clarify setup order, env vars, and test commands.
- Out of scope: backend feature changes.

## Required Changes
1. Expand setup steps in `README.md`.
2. Add a short troubleshooting section with common failures.

## Validation
- Commands to run:
  - `pytest tests/ -v`
- Manual verification:
  - Setup section includes a complete copy/paste command sequence.

## Deliverables
- Expected files to change: `README.md`
- Expected commit message style: `docs: ...`

## Acceptance Criteria
- [ ] README setup section is complete and ordered.
- [ ] Troubleshooting section includes at least 3 common issues.
- [ ] Test command remains accurate for the repo.
```
