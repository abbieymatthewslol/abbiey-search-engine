# Task Definition Template for Agent Runs

Use this when opening an issue, triggering automation, or handing off work to an agent.

## 1) Objective
One sentence stating the user-visible outcome.

## 2) Background
Relevant context (links, related PRs/issues, environment constraints, feature flags, etc.).

## 3) Requirements
- Functional:
  - 
- Non-functional (performance, security, privacy, compatibility):
  - 

## 4) Explicit boundaries
- Allowed files/directories:
  - 
- Forbidden files/directories:
  - 
- No-go actions (e.g., schema changes, dependency upgrades, force-push):
  - 

## 5) Validation checklist
- [ ] Unit/integration tests to run:
  - 
- [ ] Manual checks:
  - 
- [ ] Lint/type checks:
  - 

## 6) Acceptance criteria
- [ ] Behavior change is observable and matches objective
- [ ] Tests relevant to changed area pass
- [ ] No unrelated files changed
- [ ] Commit message clearly states root cause/fix

## 7) Output format expectations
Tell the agent how to report results (e.g., "findings first", include file paths, include test command output summary).

---

## Copy/paste prompt examples

### Bug fix prompt
Fix login callback failures in `app.py` for Google OAuth state validation. Keep changes limited to auth callback flow and related tests. Add/adjust tests under `tests/` to reproduce and verify the fix. Run `pytest tests/ -v`. Do not modify unrelated UI files.

### Reliability prompt
Investigate flaky tests in `tests/test_feedback.py`. Root-cause the nondeterminism and make the tests deterministic without adding arbitrary sleeps. Keep production code changes minimal and justified. Run full `pytest tests/ -v`.

### Docs-only prompt
Update automation/runbook documentation for blank trigger prompts. Keep changes docs-only (`README.md`, automation templates, `.github/agents/*`). No app code or dependency changes.

---

## Fallback when prompt is blank

If the incoming task text is empty or vague (for example: "idk what to put here"), default to:
1. verify automation templates exist and are discoverable from `README.md`;
2. improve examples/acceptance-criteria wording if needed;
3. avoid risky code changes unless there is an obvious, small, repo-health blocker.
