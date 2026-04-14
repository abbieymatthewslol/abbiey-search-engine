# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

If a scheduled automation run has an empty or unclear prompt, start from [`AUTOMATION_TASK_TEMPLATE.md`](./AUTOMATION_TASK_TEMPLATE.md).

- Copy the template into the automation prompt.
- Fill in the objective, scope, acceptance criteria, and verification commands.
- Include branch + output expectations so runs stay deterministic and auditable.
