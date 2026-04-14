# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

If you are creating or editing a cron/webhook automation for this repo, use
[`AUTOMATION_TASK_TEMPLATE.md`](./AUTOMATION_TASK_TEMPLATE.md) as the source of
truth for prompt structure, validation commands, and acceptance criteria.

Minimum quality bar for automation prompts:

- Define one concrete objective.
- Name specific files or subsystems to touch.
- Include required validation commands (for example `pytest tests/ -v`).
- Provide testable acceptance criteria.
