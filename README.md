# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

When this repository is executed by scheduled or event-driven agents, provide a concrete task definition so runs can make targeted progress.

- Quick start template: [`AUTOMATION_TASK_TEMPLATE.md`](./AUTOMATION_TASK_TEMPLATE.md)
- Expanded task-definition examples: [`.github/agents/TASK_DEFINITION_TEMPLATE.md`](./.github/agents/TASK_DEFINITION_TEMPLATE.md)

If a trigger payload is empty or vague (for example, "idk what to put here"), the safe default is:
1. Verify automation guidance files exist and are current.
2. Apply only small, low-risk documentation improvements.
3. Avoid speculative feature work without explicit requirements.
