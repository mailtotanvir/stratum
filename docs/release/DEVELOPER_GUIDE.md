# Developer Guide

## Backend

- FastAPI serves the runtime API.
- `backend/app/main.py` registers the public routers.
- Public API behavior should remain consistent with the release documentation.
- Tests live in `backend/tests/`.

## Desktop

- The console is a React/Vite app in `desktop/`.
- `desktop/src/api/runtime.ts` is the typed API boundary for the UI.
- Build with `npm run build` or the project equivalent in the desktop folder.

## Release Rules

- Do not add new platform capabilities in RC1.
- Fix only release-blocking defects.
- Keep API names, route shapes, and response models stable.
- Preserve determinism across replay and projection rebuild paths.
