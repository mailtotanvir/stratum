# API Reference

## Conventions

- The backend exposes HTTP JSON endpoints.
- The desktop uses the typed API client in `desktop/src/api/runtime.ts`.
- The release candidate does not introduce a versioned `/v1` route prefix.
- Route names are intentionally descriptive and domain-specific.

## Core Routes

- `/health`
- `/runtime/status`
- `/runtime/dashboard`
- `/runtime/workspaces`
- `/runtime/sessions/{session_id}/artifacts`
- `/runtime/projections/replay`
- `/runtime/query-execute`
- `/agent-loop/run`
- `/agent-loop/smoke`
- `/providers/health`
- `/providers/live/diagnostics`
- `/providers/live/verify`
- `/runtime/providers/observability`
- `/artifacts`
- `/evaluations`

## Limitations

- Some read models expose both runtime-prefixed and direct aliases for backward compatibility.
- The API is intentionally local-first and optimized for the WSL desktop deployment model.
