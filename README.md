# abbiey.search

Private, fast search with no query logging and no third-party trackers. Built with Python and Flask; see `CLAUDE.md` for the full stack, features, and how to run the app locally.

## Automation

If an automation trigger runs without a clear request, use `AUTOMATION_TASK_TEMPLATE.md` to provide a concrete task. This helps background runs avoid no-op prompts like "idk what to put here."

Quick copy/paste for automation prompts:

```md
Goal: <one clear objective>
Context: <links/files/incidents>
Constraints: <what to avoid or preserve>
Definition of done:
- <checkable result 1>
- <checkable result 2>
Verification:
- <tests or commands to run>
```

For full guidance and examples, see [`AUTOMATION_TASK_TEMPLATE.md`](./AUTOMATION_TASK_TEMPLATE.md).
