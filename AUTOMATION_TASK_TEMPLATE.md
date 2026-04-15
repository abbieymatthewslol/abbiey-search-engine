# Automation Task Definition Template

Use this when configuring cron/webhook automation runs. The agent performs best when the task includes a clear goal, exact scope, and concrete success criteria.

## Copy/Paste Template

```md
## Goal
<one specific outcome>

## Scope
- Branch: <required branch name>
- Files/areas allowed to change: <paths or modules>
- Explicitly out of scope: <what should not be touched>

## Constraints
- Keep changes minimal and reversible
- Do not add new dependencies unless required
- Preserve existing behavior outside the scoped area

## Acceptance Criteria
1. <observable result 1>
2. <observable result 2>
3. <tests/checks that must pass>

## Verification
Run and report:
- <command 1>
- <command 2>

## Deliverable
- Commit changes on the current task branch
- Push to origin
- Summarize what changed and why
```

## Good Prompt Examples

### Example 1: Tight bugfix

```md
## Goal
Fix the syntax/indentation error in app.py that blocks pytest collection.

## Scope
- Branch: abbieymatthewslol/task-definition-needed-1217
- Files: app.py and affected tests only
- Out of scope: UI/CSS changes and unrelated refactors

## Constraints
- Smallest safe patch
- No behavior changes beyond restoring valid startup/import

## Acceptance Criteria
1. `python -m py_compile app.py` succeeds
2. `pytest tests/ -q` runs without syntax errors
3. Any touched tests reflect the intended behavior

## Verification
- python -m py_compile app.py
- pytest tests/ -q
```

### Example 2: Docs-only maintenance

```md
## Goal
Improve README onboarding instructions for local development.

## Scope
- Files: README.md only
- Out of scope: application code and dependency updates

## Acceptance Criteria
1. README has a clear setup section with exact commands
2. Existing instructions are preserved or clarified, not removed blindly
3. Changes are docs-only and easy to review

## Verification
- Review rendered markdown for formatting
```

## Avoid These Prompts

- "idk what to put here"
- "fix stuff"
- "do some cleanup"
- "make this better"

These are too vague to execute safely.

## Minimum Quality Bar

Before saving an automation prompt, confirm:

- [ ] One concrete goal is defined
- [ ] Scope names specific files or modules
- [ ] Non-goals/out-of-scope items are explicit
- [ ] Success is measurable with checks or tests
- [ ] Deliverable expectations are included
