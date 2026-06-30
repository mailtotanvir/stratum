# Codex Workflow Note

Use this note to shape future `next` prompts for Stratum v1.0.

## Operating Rules

- Future `next` prompts should select the next epic or continue the active epic.
- Codex should work to milestone completion inside the epic boundary.
- Avoid tiny file-level or git-hygiene prompts unless they are needed to unblock commit safety.
- Prefer a single bounded epic slice over many micro tasks.
- Keep the event-store-first architecture and adapter boundaries intact.

## Prompt Shape

Good:
```text
Continue Epic 4: Workspace & Repository Operations.
Work only within the epic boundary.
Complete the next milestone slice and stop at a stable checkpoint.
```

Avoid:
```text
Touch a few files and fix git noise.
```

