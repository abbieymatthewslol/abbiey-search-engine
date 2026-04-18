# Task Definition Template

Use this when opening issues, assigning an agent run, or preparing automation prompts.

## Quick Version

```md
Task:
- <exact change required>

Acceptance:
- [ ] <clear outcome 1>
- [ ] <clear outcome 2>

Verify:
- <command or manual check>
```

## Full Version

```md
## Objective
<what should be built/fixed>

## Context
<why this work is needed>

## In Scope
- <file/feature>
- <file/feature>

## Out of Scope
- <explicit non-goal>

## Constraints
- <backward compatibility, security, runtime, etc.>

## Acceptance Criteria
- [ ] <observable behavior change>
- [ ] <tests/docs updated if applicable>

## Verification Steps
- Commands:
  - `<command>`
- Manual:
  - <manual check>
```

## If You Only Have a Vague Idea

If your first draft is “idk what to put here”, use this seed prompt:

```md
Task:
- Audit the repo for one safe, docs-only improvement that reduces confusion for future automation runs.

Acceptance:
- [ ] A missing or unclear automation instruction is added/clarified.
- [ ] No runtime behavior changes.

Verify:
- git diff shows docs-only edits.
```
