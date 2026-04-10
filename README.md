# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

For cron/webhook automation runs, define the task using
[`AUTOMATION_TASK_TEMPLATE.md`](./AUTOMATION_TASK_TEMPLATE.md). This helps avoid
empty prompts and ensures each run includes objective, scope, validation, and
acceptance criteria.
