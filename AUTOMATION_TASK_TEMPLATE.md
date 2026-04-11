# Automation Task Template

Use this template when configuring cron/webhook automation runs so each trigger has a concrete, testable task.

## Copy/Paste Prompt

```md
## Objective
<One sentence with the exact change to make.>

## Scope
- In scope:
  - <specific file or subsystem>
  - <specific file or subsystem>
- Out of scope:
  - <what should not be changed>

## Required Changes
1. <step 1 with expected behavior>
2. <step 2 with expected behavior>
3. <step 3 with expected behavior>

## Acceptance Criteria
- [ ] <observable condition that must be true>
- [ ] <observable condition that must be true>
- [ ] <tests/docs updated if relevant>

## Validation Commands
Run and report results for:
- `pytest tests/ -v`
- <extra command if needed>

## Constraints
- Do not change branch.
- Keep secrets out of commits.
- Keep changes minimal and focused.
```

## Good Example

```md
## Objective
Document the search ranking fallback flow in `project-index.md`.

## Scope
- In scope:
  - `project-index.md`
  - `README.md` (link to the new section)
- Out of scope:
  - Runtime logic in `app.py`
  - Frontend behavior in `static/`

## Required Changes
1. Add a short "Ranking Fallback Flow" section to `project-index.md`.
2. Include references to the modules that implement fallback behavior.
3. Add one README bullet linking to that section.

## Acceptance Criteria
- [ ] New section exists with accurate module references.
- [ ] README includes link to the new section.
- [ ] `pytest tests/ -v` still passes.

## Validation Commands
Run and report results for:
- `pytest tests/ -v`
```

## Bad Prompt Example

Avoid prompts like:

- "idk what to put here"
- "fix stuff"
- "make it better"

These are too ambiguous for reliable automation outcomes.
