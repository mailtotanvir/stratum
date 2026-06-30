# Desktop Runtime Console

This directory contains the local desktop/dev runtime console for Stratum.

## WSL workflow

Work from the source tree in `~/stratum/desktop` inside WSL. Do not copy the repo to Windows and do not add any Windows/WSL sync step.

The backend runs in WSL at `http://127.0.0.1:8000`, and the Tauri/React desktop talks to it over HTTP and SSE.

## Start backend

From `backend/`:

```bash
uv run uvicorn app.main:app --reload
```

## Start desktop frontend

From `desktop/`:

```bash
pnpm install
pnpm dev
```

If you need a different API host, set `VITE_RUNTIME_API_BASE_URL` before starting Vite:

```bash
VITE_RUNTIME_API_BASE_URL=http://127.0.0.1:8000 pnpm dev
```

## Start Tauri

If Tauri is configured in your local checkout:

```bash
pnpm tauri dev
```

## Smoke flow

1. Open the desktop console and run a request against the backend.
2. Confirm the request appears in the session list.
3. Open the session timeline and verify the run events stream in order.
4. If the session pauses for approval, use the approval controls to approve or resume it.
5. Confirm the final answer appears in the session summary.

## Local smoke validation

Run the dependency-free console smoke check after changes to the desktop shell:

```bash
pnpm smoke
```

This checks that the main desktop navigation still exposes the Runtime Console, Session Timeline, Approvals, Provider Observability, Artifacts, and Settings panels.

## Notes

- The frontend shows a readable backend-unavailable message when the API cannot be reached.
- The source of truth stays in WSL under `~/stratum`; there is no separate Windows copy.
