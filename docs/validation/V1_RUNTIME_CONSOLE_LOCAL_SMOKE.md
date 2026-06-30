# V1 Runtime Console Local Smoke

This is the repeatable local smoke for the Stratum runtime console.

## Backend

From `backend/`:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Frontend

From `desktop/`:

```bash
pnpm dev
```

## Smoke Script

From the repository root:

```bash
scripts/runtime_console_smoke.sh
```

What it does:

- checks backend dependencies are available
- starts the backend on `127.0.0.1:8000` if it is not already running
- waits for `GET /runtime/status`
- posts a safe `POST /agent-loop/smoke` request
- fetches `GET /runtime/status`, `GET /runtime/dashboard`, and `GET /agent-loop/runs`
- prints concise pass/fail output
- exits gracefully when the live provider is not configured

## Expected Output

Successful run:

```text
runtime/status: ready
runtime/dashboard: active_sessions=...
PASS: backend is ready
PASS: smoke run completed (agent-loop-smoke-...)
agent-loop/runs: ...
```

When a live provider is not configured:

```text
runtime/status: unconfigured
runtime/dashboard: active_sessions=...
PASS: backend is reachable
SKIP: live provider is not configured (unconfigured)
Configure the default live provider in the backend, then rerun this smoke.
```

## Known Limitation

The Tauri Windows shell is manual for now. This smoke only covers the backend runtime console path and does not launch Tauri automatically.
