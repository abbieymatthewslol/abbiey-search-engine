# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

If a scheduled automation run needs a task prompt, use the template in [`AUTOMATION_TASK_TEMPLATE.md`](AUTOMATION_TASK_TEMPLATE.md).

Quick quality bar before saving a prompt:

- Include a concrete goal (what should change).
- Include affected files or subsystem hints when known.
- Include validation steps (tests or checks to run).
- Include acceptance criteria that can be verified from output.
