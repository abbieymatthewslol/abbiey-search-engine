# Task Definition Template (for Agents)

Use this when handing work to an agent or automation run. Replace placeholders with concrete details.

```md
## Task
<what needs to be done>

## Repository Context
- Branch to use: <branch-name>
- Base branch: <master/main/etc.>
- Files likely involved:
  - <path 1>
  - <path 2>

## Requirements
- Functional requirements:
  1. <requirement 1>
  2. <requirement 2>
- Non-functional constraints:
  - <performance/security/compatibility constraint>

## Acceptance Criteria
- [ ] <user-visible outcome>
- [ ] <edge case outcome>
- [ ] Validation run:
  - `<command 1>`
  - `<command 2>`

## Definition of Done
- [ ] Code updated
- [ ] Tests updated or justified not needed
- [ ] Changelog/docs updated if behavior changed
- [ ] Commit pushed to the requested branch
```

## Fallback for Empty or Vague Prompts

If the incoming request is blank or vague (for example: "idk what to put here"), default to:

1. **Low-risk maintenance** only (docs, guardrails, templates, small clarity fixes).
2. Prefer improvements that reduce future ambiguity (task templates, explicit acceptance criteria examples).
3. Avoid speculative feature work without clear requirements.
