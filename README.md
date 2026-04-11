# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

If you are triggering a Cursor automation (cron, webhook, or manual run), provide a concrete task using [`AUTOMATION_TASK_TEMPLATE.md`](./AUTOMATION_TASK_TEMPLATE.md).

At minimum, include:

- **Goal**: what should change
- **Scope**: files or subsystems that can be touched
- **Done criteria**: how success is verified (tests, checks, or behavior)

If no actionable task is provided, the automation will default to safe docs maintenance instead of product code changes.
