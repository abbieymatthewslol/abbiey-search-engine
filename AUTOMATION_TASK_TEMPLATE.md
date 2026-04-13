# Automation Task Prompt Template

Use this template for cron/webhook runs so the agent receives a clear, testable objective.

## Copy/paste template

```md
## Goal
<What outcome should this run produce?>

## Scope
- In scope: <files/systems that may change>
- Out of scope: <what should not be touched>

## Acceptance Criteria
- [ ] <observable behavior/result 1>
- [ ] <observable behavior/result 2>

## Validation
- Run: `<command>`
- Confirm: <expected output/signal>

## Constraints (optional)
- <branch, dependency, deployment, or security constraints>
```

## Minimal example

```md
## Goal
Fix failing Python CI lint job.

## Scope
- In scope: Python syntax/lint errors in app and tests
- Out of scope: new features

## Acceptance Criteria
- [ ] Flake8 fatal checks pass
- [ ] No behavior change beyond syntax/lint fix

## Validation
- Run: `python3 -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
- Confirm: command exits 0
```

## Prompt quality bar

Before saving an automation prompt, confirm it answers:
1. What should be changed?
2. How do we know it worked?
3. What must remain unchanged?
