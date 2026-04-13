# Automation Task Template

Use this file when a cron/manual automation run needs a clear task prompt.

## Quick copy/paste prompt

```md
## Goal
<What should change and why?>

## Scope
- In scope: <files/features allowed to change>
- Out of scope: <what must not change>

## Constraints
- Keep changes limited to <area>.
- Do not add new dependencies unless required.
- Preserve existing behavior outside the requested change.

## Acceptance Criteria
1. <measurable outcome 1>
2. <measurable outcome 2>
3. Tests/checks pass: <exact command(s)>

## Validation
- Run: <command 1>
- Run: <command 2>

## Deliverable
- Commit and push code changes to the current task branch.
- Include a short summary of what changed and why.
```

## Example prompts for this repository

### Example 1: bug fix

```md
Goal: Fix keyboard navigation regression in result preview panel.
Scope: static/script.js and tests related to keyboard navigation only.
Constraints: Do not change styling or unrelated search behavior.
Acceptance Criteria:
1. j/k navigation moves selection reliably after infinite scroll append.
2. Hover preview still works as before.
3. pytest tests/ -v passes.
Validation:
- pytest tests/ -v
```

### Example 2: docs-only task

```md
Goal: Improve local setup docs for Supabase connection troubleshooting.
Scope: README.md and/or CLAUDE.md docs sections only.
Constraints: No code or dependency changes.
Acceptance Criteria:
1. Include explicit check commands and expected output snippets.
2. Keep instructions consistent with current scripts in scripts/.
Validation:
- Manual review for correctness and clarity.
```

## If you do not know what to request

Use this minimal safe prompt:

```md
Goal: Run a quick repository health check and fix only low-risk docs issues.
Scope: docs files only unless tests reveal a trivial fix.
Acceptance Criteria:
1. Report git status and test/check outcomes.
2. If no actionable issue is found, make no code changes and summarize findings.
```
