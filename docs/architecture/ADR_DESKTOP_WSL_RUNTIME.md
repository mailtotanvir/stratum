# ADR: Desktop WSL Runtime Boundary

## Status

Accepted

## Context

Stratum's desktop experience is being prepared as a Windows desktop shell while the source tree and backend runtime remain in WSL.

We need a minimal, stable boundary that supports the current workflow without introducing Windows file synchronization, repository duplication, or backend changes.

## Decision

- The repository and source of truth remain in WSL under `~/stratum`.
- The FastAPI runtime continues to run in WSL.
- The desktop shell is a Windows Tauri app that renders the React/Vite UI.
- The UI communicates with the backend over `http://127.0.0.1:8000` by default.
- Real-time runtime updates use HTTP and SSE against localhost.
- No Windows copy/sync step is required or introduced.
- CLI/TUI remains a future optional operator surface and is not part of this boundary.

## Consequences

- Desktop development can proceed without moving the repository into Windows.
- The default API base URL stays stable for local WSL development.
- The desktop shell can be added incrementally without forcing backend packaging or filesystem migration work.
- Any Tauri scaffold should stay minimal and avoid rewriting existing runtime or API configuration unless a real desktop packaging requirement appears.

## Notes

- This ADR only defines the runtime boundary and operating model.
- It does not require `src-tauri` to exist today.
- It does not require Windows-native backend execution or a sync bridge.
