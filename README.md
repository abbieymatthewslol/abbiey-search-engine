# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

If an automation trigger provides an undefined task (for example: "idk what to put here"), use the repository task templates instead of guessing:

- `AUTOMATION_TASK_TEMPLATE.md` - quick default task definition for routine runs.
- `.github/agents/TASK_DEFINITION_TEMPLATE.md` - richer copy/paste template with scope, constraints, and acceptance criteria.

When the prompt is blank or vague, restore/improve these templates first so future runs become actionable.
