# Task Definition Template (Agent-Friendly)

Use this file when writing automation prompts or handing work to an autonomous coding agent.

## 1) Minimal Reliable Task

```md
Goal: <single concrete outcome>

Context:
- Repo area: <paths/modules>
- Relevant constraints: <security/perf/deploy limits>

Do:
1. <step 1>
2. <step 2>
3. <step 3>

Done when:
- [ ] <verification #1>
- [ ] <verification #2>
- [ ] <tests/commands and expected result>
```

## 2) Strong Task (Preferred)

```md
## Goal
<What should be true after this run?>

## Context
- Background:
  - <important details, links, prior attempts>
- Affected paths:
  - <path>
  - <path>

## Requirements
1. <required change>
2. <required change>
3. <required change>

## Non-goals
- <what not to do>
- <what not to do>

## Validation
- Run: `<command>`
- Run: `<command>`
- Confirm:
  - [ ] <observable behavior>
  - [ ] <observable behavior>

## Commit expectations
- Commit message style: `<example>`
- Keep commit scope: `<small/single logical change>`
```

## 3) Examples

### Example A — Bugfix

```md
## Goal
Fix regression where `/api/preview` returns 500 for invalid URLs.

## Context
- Affected paths:
  - app.py
  - tests/test_preview_api.py
- Keep existing API response shape.

## Requirements
1. Handle invalid/empty URL inputs with 400 response.
2. Preserve current success response schema.
3. Add/adjust pytest coverage for invalid input.

## Non-goals
- No UI redesign.
- No unrelated refactor.

## Validation
- Run: `pytest tests/test_preview_api.py -v`
- Confirm:
  - [ ] Invalid URL returns 400.
  - [ ] Valid URL still returns metadata payload.
```

### Example B — Blank Prompt Fallback

```md
## Goal
Recover from missing automation task definition.

## Context
Automation text is vague (example: "idk what to put here").

## Requirements
1. Ensure these files exist and are current:
   - AUTOMATION_TASK_TEMPLATE.md
   - .github/agents/TASK_DEFINITION_TEMPLATE.md
   - README.md automation pointer
   - .github/agents/my-agent.agent.md blank-task fallback
2. Prefer docs-only edits.
3. Keep changes focused and low-risk.

## Validation
- Run: `git status --short`
- Confirm:
  - [ ] Only expected docs files changed.
  - [ ] Templates include acceptance criteria examples.
```
