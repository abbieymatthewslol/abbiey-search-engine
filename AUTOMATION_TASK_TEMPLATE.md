# Automation Task Template

Use this template when creating automation prompts (cron, webhook, or manual runs).  
Clear inputs prevent no-op runs and reduce branch churn.

## Copy/Paste Prompt

```md
## Objective
<One sentence describing what outcome is needed>

## Context
- Branch: <current branch>
- Related files/modules: <paths or "unknown">
- Related issue/PR: <link or "none">

## Scope
- In scope:
  - <item 1>
  - <item 2>
- Out of scope:
  - <item 1>

## Requirements
1. <behavioral requirement>
2. <compatibility/security/testing requirement>

## Acceptance Criteria
- [ ] <observable result 1>
- [ ] <observable result 2>
- [ ] `pytest tests/ -v` (or explain why skipped)

## Deliverables
- Code and/or docs changes committed to the current task branch
- Brief summary of what changed
- Risks or follow-ups (if any)
```

## Minimal Example

```md
## Objective
Fix flaky retrieval test failures caused by shared analytics rows.

## Context
- Branch: abbieymatthewslol/task-definition-needed-xxxx
- Related files/modules: tests/test_feedback_rerank.py
- Related issue/PR: none

## Scope
- In scope:
  - Make flaky tests deterministic by isolating query keys per run.
- Out of scope:
  - Refactoring ranking logic.

## Requirements
1. Preserve current feature behavior.
2. Keep test runtime close to baseline.

## Acceptance Criteria
- [ ] Targeted test file passes locally.
- [ ] Full `pytest tests/ -v` passes or failures are documented.
```

