# Automation Task Template

Use this template when configuring cron/webhook/background automation so each run has a clear, actionable goal.

## Copy/Paste Prompt

```md
Goal: <one concrete outcome>

Context:
- Why this should be done now
- Relevant files/components
- Related issue/PR links (if any)

Requirements:
- Required code/docs changes
- Constraints (security, performance, compatibility, no new deps, etc.)
- Explicitly out-of-scope items

Validation:
- Commands the agent must run (tests, linters, scripts)
- Expected result for each command

Deliverable:
- What to report back (summary, risks, follow-ups)
```

## Good Prompt Examples

1. "Fix failing `tests/test_auth.py::test_google_oauth_callback` by updating the callback handler and add regression coverage."
2. "Add `Cache-Control` headers for static assets in Flask responses without changing CSP behavior; verify with existing tests."
3. "Document how to rotate Supabase keys in `CLAUDE.md` and `AGENTS.md`, then run markdown lint checks."

## Notes for Maintainers

- If the automation trigger is recurring, keep prompts narrow and idempotent.
- Prefer one objective per run; split unrelated goals into separate automations.
- Include exact verification commands to reduce ambiguous outputs.
