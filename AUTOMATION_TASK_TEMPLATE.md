# Automation Task Template

Use this template when configuring cron/webhook automations so each run has a concrete objective.

## Copy/Paste Task Prompt

```md
Goal:
- <one-sentence outcome>

Scope:
- In scope: <files/modules/areas>
- Out of scope: <what to avoid changing>

Definition of done:
- [ ] Code/docs updated
- [ ] Relevant tests run (list exact commands)
- [ ] Changes committed and pushed to the current automation branch
- [ ] Brief summary of what changed and why

Constraints:
- Keep changes small and safe
- Do not add secrets
- Do not change deployment targets/remotes

Verification commands:
- <command 1>
- <command 2>
```

## Good Prompt Examples

1. **Docs quality pass**
   - Goal: Improve developer onboarding docs for local setup.
   - Scope: `README.md` and `CLAUDE.md` only.
   - Done: both files updated, links verified, no code touched.

2. **Test stabilization**
   - Goal: Fix flaky test behavior in search ranking tests.
   - Scope: `tests/` plus minimal production code needed.
   - Done: failing test reproduced, fix implemented, `pytest tests/ -v` passes.

3. **Small bugfix**
   - Goal: Fix crash when suggestions API gets empty query.
   - Scope: route handler + tests.
   - Done: bug fixed, regression test added, test suite green.

## If You Do Not Know What to Put

Start with this:

```md
Goal:
- Do a safe maintenance pass for prompt quality and automation docs.

Scope:
- In scope: `AUTOMATION_TASK_TEMPLATE.md`, `.github/agents/TASK_DEFINITION_TEMPLATE.md`, `README.md`, `.github/agents/my-agent.agent.md`
- Out of scope: application logic and dependency changes

Definition of done:
- [ ] Missing templates are created or refreshed
- [ ] README points to the templates
- [ ] Agent instructions include fallback behavior for vague prompts
```
