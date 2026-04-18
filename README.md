# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

When creating scheduled or webhook-triggered agent runs, use:

- `AUTOMATION_TASK_TEMPLATE.md` (repo root) for end-to-end run prompts.
- `.github/agents/TASK_DEFINITION_TEMPLATE.md` for concise issue/agent task specs.

If your first draft is vague (for example, "idk what to put here"), start from the seed prompt in `.github/agents/TASK_DEFINITION_TEMPLATE.md` and make the objective, scope, and verification explicit before running automation.
