# Automation Task Prompt Template

Use this when creating cron/webhook automation prompts for this repository.

## Copy/Paste Template

```md
Goal:
- [What should be achieved?]

Context:
- [Why this matters now]
- [Related issue/PR links, if any]

Scope:
- In scope:
  - [Specific files/systems to touch]
- Out of scope:
  - [What should not be changed]

Definition of Done:
- [ ] Behavior change is implemented
- [ ] Relevant tests are updated or added
- [ ] `pytest tests/ -v` passes (or explain why skipped)
- [ ] Docs updated if user-facing behavior changed
- [ ] Changes committed and pushed to the working branch

Constraints:
- [Security/performance/privacy constraints]
- [Dependency constraints]

Deliverable:
- [What should be included in the final agent response]
```

## Minimal Example (Bug Fix)

```md
Goal:
- Fix Google OAuth button doing nothing on login page.

Context:
- Production users report no redirect after clicking "Continue with Google".

Scope:
- In scope:
  - templates/login.html
  - app.py CSP header logic
- Out of scope:
  - Styling changes
  - Signup flow redesign

Definition of Done:
- [ ] OAuth button redirects to Supabase authorize URL
- [ ] Inline scripts remain CSP-compliant with nonce
- [ ] Existing auth tests pass

Constraints:
- Keep strict CSP (no `unsafe-inline`).

Deliverable:
- Short summary, changed files, and verification steps run.
```

## If You Are Unsure What To Ask

Use this fallback:

```md
Goal:
- Perform low-risk maintenance.

Scope:
- In scope:
  - Documentation quality improvements
  - Broken links, outdated setup notes, typo fixes
- Out of scope:
  - Feature work
  - Large refactors

Definition of Done:
- [ ] At least one concrete docs improvement is merged-ready
- [ ] No behavior changes introduced
```
