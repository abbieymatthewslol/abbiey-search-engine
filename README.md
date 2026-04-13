# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

When starting a scheduled/background run, provide a concrete task prompt so the agent can act deterministically.

- Use: `AUTOMATION_TASK_TEMPLATE.md`
- Include a goal, scope, acceptance criteria, and validation command(s)
- Avoid placeholders like "idk what to put here"
