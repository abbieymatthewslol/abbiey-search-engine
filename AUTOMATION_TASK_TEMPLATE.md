# Automation Task Prompt Template

Use this when creating or updating a cron/webhook automation prompt so runs are actionable.

## Copy/Paste Skeleton

```md
## Objective
<One concrete outcome. Example: "Add a fallback timeout to DDG image search requests in app.py.">

## Scope
- In scope:
  - <files/modules allowed to change>
- Out of scope:
  - <what should not change>

## Constraints
- Keep behavior backwards compatible unless explicitly stated.
- Do not add new dependencies unless required.
- Follow repo conventions in AGENTS.md and CLAUDE.md.

## Validation
- Run: <exact test commands>
- Manually verify: <specific user-visible behavior>

## Acceptance Criteria
- [ ] <verifiable requirement 1>
- [ ] <verifiable requirement 2>
- [ ] <logs/screenshots/output expected, if any>

## Deliverables
- Commit(s) pushed to: <branch name>
- Short summary of what changed and why
```

## Good Prompt Example

```md
## Objective
Document how to write actionable automation prompts for this repo.

## Scope
- In scope:
  - README.md
  - AUTOMATION_TASK_TEMPLATE.md
- Out of scope:
  - Python app behavior
  - Frontend JavaScript/CSS

## Constraints
- Docs-only change.
- Keep instructions concise and copy/paste friendly.

## Validation
- Confirm README links to AUTOMATION_TASK_TEMPLATE.md.
- Confirm template includes objective, scope, validation, and acceptance criteria sections.

## Acceptance Criteria
- [ ] README has an Automation section with template link.
- [ ] Template exists at repo root and contains a complete prompt skeleton.
```

## Anti-Patterns to Avoid

- "idk what to put here"
- "fix stuff"
- "improve performance" (without subsystem, metric, or validation)
- Missing validation or acceptance criteria
