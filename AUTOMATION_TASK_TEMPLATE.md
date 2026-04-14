# Automation Task Prompt Template

Use this template when creating cron/webhook/PR-triggered runs so the agent gets an actionable task.

## Copy/Paste Template

```md
## Objective
<One concrete result. Example: "Harden query parsing fallback for malformed operators.">

## Scope
- In scope:
  - <file/module/area 1>
  - <file/module/area 2>
- Out of scope:
  - <explicitly excluded work>

## Constraints
- Keep changes on branch: <branch-name>
- Do not modify: <sensitive paths, if any>
- Dependency policy: <none / allowed package manager>

## Acceptance Criteria
- [ ] <observable behavior or requirement 1>
- [ ] <observable behavior or requirement 2>
- [ ] Tests added/updated where applicable
- [ ] Existing tests still pass

## Verification Commands
Run and report output for:
- `<command 1>`
- `<command 2>`

## Deliverables
- Summary of what changed (files + behavior)
- Risks / follow-ups (if any)
- Commit message(s) used
```

## Quality Bar Checklist

Before triggering automation, ensure the prompt:

1. Names a specific objective (not "fix stuff" or "improve app").
2. Defines boundaries (what to change and what to avoid).
3. Includes measurable acceptance criteria.
4. Lists verification commands the agent should run.
5. States expected output format for easy review.

## Example (Cron Prompt)

```md
Objective: Reduce noisy weather-card failures in entity detection.
Scope: `entity_parser.py`, `tests/test_entity_parser.py`; no frontend changes.
Acceptance criteria:
- Queries like "weather in London?" parse weather intent correctly.
- Non-weather queries do not regress.
- `pytest tests/test_entity_parser.py -v` passes.
Deliverables: commit + push, plus short summary of behavior changes.
```
