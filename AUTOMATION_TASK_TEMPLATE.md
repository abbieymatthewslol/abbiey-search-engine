# Automation Task Template

Use this template when configuring cron/webhook/manual automation prompts for
this repository.

## Copy/Paste Prompt

```md
Objective:
- <one concrete outcome, e.g. "Fix flaky test in tests/test_auth.py">

Scope:
- In scope: <files/components allowed to change>
- Out of scope: <what must not be touched>

Constraints:
- Keep CSP nonce pattern intact for inline scripts (`nonce="{{ csp_nonce }}"`).
- Do not change deployment targets, secrets, or git remotes.
- Prefer minimal, reversible changes.

Acceptance Criteria:
1. <observable behavior/result>
2. <tests/checks to run>
3. <documentation updated if behavior changes>

Validation Commands:
- <command 1>
- <command 2>

Deliverable:
- Commit changes on the automation branch and push to origin.
- Provide a short summary of edits, validation output, and risks.
```

## Good Prompt Examples

1. **Bug fix**
   - "Fix `/auth/callback` 500 when `display_name` is missing; add regression
     test and run `pytest tests/test_auth.py -v`."
2. **Refactor with guardrails**
   - "Refactor duplicated weather-card formatter in `static/script.js` only,
     no UI changes; run frontend smoke checks from `tests/MANUAL_QA_LAYOUT.md`."
3. **Docs maintenance**
   - "Update Supabase onboarding steps in `CLAUDE.md` and `AGENTS.md` to match
     current project ref and health-check commands."

## If You Are Unsure What To Ask For

Use this fallback prompt:

> "Perform a docs-only maintenance pass: find one stale or missing operator
> guide related to current workflows, update it, and summarize why it matters.
> Do not modify application logic."
