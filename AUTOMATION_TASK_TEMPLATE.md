# Automation Task Template

Use this template when triggering automated runs so the agent has enough detail to make safe, useful changes.

## Copy/Paste Template

```md
## Goal
<What outcome do you want? Be explicit about behavior or deliverable.>

## Context
<Why this matters, links to issue/PR/docs, and any constraints.>

## Scope
- In scope:
  - <files, modules, or areas allowed to change>
- Out of scope:
  - <things the agent must not change>

## Acceptance Criteria
- [ ] <observable requirement 1>
- [ ] <observable requirement 2>
- [ ] <required tests/checks to run>

## Validation Commands
<exact commands the agent should run, e.g. `pytest tests/test_auth.py -q`>

## Delivery Notes
<branch requirements, commit style, rollout notes, or follow-ups>
```

## Good Example

```md
## Goal
Fix Google OAuth sign-in button regression on login/signup pages.

## Context
Users report "Continue with Google" does nothing in production.

## Scope
- In scope:
  - `app.py` CSP nonce/header logic
  - `templates/login.html`
  - `templates/signup.html`
- Out of scope:
  - billing flows
  - search ranking logic

## Acceptance Criteria
- [ ] Clicking Google button redirects to Supabase authorize URL
- [ ] No CSP inline-script violations in browser console
- [ ] `pytest tests/test_auth.py -q` passes

## Validation Commands
pytest tests/test_auth.py -q
```

## Minimal Prompt (if you are in a hurry)

```md
Goal: <one sentence>
Scope: <what files/areas can change>
Done when: <how to verify>
```

Avoid prompts like "idk what to put here" because they do not provide actionable intent.
