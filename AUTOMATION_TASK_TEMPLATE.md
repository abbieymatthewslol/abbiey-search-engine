# Automation Task Template

Use this template when creating or updating automation prompts (cron, webhook, PR trigger, etc.).

## Task Summary
- One sentence describing what should be done.

## Goal
- What outcome should exist when the run is complete.

## Scope
- In scope:
  - List exact files, folders, or subsystems.
- Out of scope:
  - List areas that must not change.

## Inputs and Context
- Relevant issue/PR links:
- Relevant files:
- Known constraints (security, compatibility, deployment):

## Required Work
1. Concrete step 1
2. Concrete step 2
3. Concrete step 3

## Validation
- Commands to run:
  - `pytest tests/ -v`
  - (add others if needed)
- Manual checks:
  - Check 1
  - Check 2

## Deliverables
- Files expected to change:
- Expected commit message style:
- Any artifacts to attach (logs/screenshots):

## Definition of Done
- [ ] Changes implemented
- [ ] Validation completed
- [ ] Commit created
- [ ] Branch pushed
- [ ] PR opened/updated if required

## Copy/Paste Starter Prompt
Use this exact starter text when a run needs a quick but actionable prompt:

```
Task: <what to change>
Goal: <expected outcome>
Scope: <files/areas allowed>
Constraints: <what must not break>
Validation: <commands/checks>
Deliverables: <commits/tests/notes>
```
