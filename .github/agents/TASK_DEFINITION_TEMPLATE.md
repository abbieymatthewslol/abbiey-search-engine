# Detailed Task Definition Template

Copy/paste this template when creating or repairing an automation prompt.

## 1) Problem Statement
What is wrong right now? Include one concrete symptom.

Example:
- Cron runs often contain placeholder text, so the agent has no actionable work.

## 2) Desired Outcome
What should be true after this task is complete?

Example:
- Repo includes clear fallback templates and agent guidance for blank/vague prompts.

## 3) Scope
### In scope
- Specific files to edit
- Specific tests/scripts to run

### Out of scope
- Unrelated refactors
- New feature development not needed for the fix

## 4) Constraints
- Keep changes low-risk and production-safe.
- Prefer docs/tests/obvious bug fixes over speculative product changes.
- Follow existing branch and commit policies.

## 5) Implementation Notes
List exact requirements, naming, or style rules the agent should follow.

## 6) Validation
Define concrete checks:
- Commands to run (for example, `pytest tests/ -v`)
- Expected result

## 7) Deliverables
- Summary of changes
- Files touched
- Verification evidence
- Remaining risks (if any)

## 8) Optional Context
- Related issue/PR links
- Known regressions
- Environment constraints
