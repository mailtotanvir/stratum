# V1 Runtime UI Integration Validation

## Scope

- Desktop frontend scripts
- Frontend dependency install
- Frontend build/typecheck/test entrypoint from `desktop/package.json`
- Backend focused API tests
- Patch integrity check with `git diff --check`

## Commands Run

### Desktop scripts

```bash
sed -n '1,220p' desktop/package.json
```

Observed scripts:

- `dev`: `vite`
- `build`: `tsc -b && vite build`
- `preview`: `vite preview`

### Frontend dependency install

```bash
mkdir -p /tmp/codex-pnpm-home /tmp/codex-pnpm-store /tmp/codex-uv-cache && XDG_CONFIG_HOME=/tmp/codex-config XDG_CACHE_HOME=/tmp/codex-cache PNPM_HOME=/tmp/codex-pnpm-home pnpm config set store-dir /tmp/codex-pnpm-store && XDG_CONFIG_HOME=/tmp/codex-config XDG_CACHE_HOME=/tmp/codex-cache PNPM_HOME=/tmp/codex-pnpm-home pnpm install
```

Result:

- Failed due environment/network access.
- `pnpm` could not resolve `registry.npmjs.org`:
  - `ERR_PNPM_META_FETCH_FAIL`
  - `getaddrinfo EAI_AGAIN registry.npmjs.org`

### Backend focused API tests

```bash
cd backend && UV_CACHE_DIR=/tmp/codex-uv-cache uv run pytest tests/test_agent_loop_route.py tests/test_runtime_dashboard.py tests/test_runtime_session_overview.py tests/test_runtime_timeline.py tests/test_runtime_status.py tests/test_provider_observability.py -q
```

Result:

- Could not complete in this environment.
- `uv` initially failed before test execution because its default cache path was not writable.
- The run was redirected to `/tmp`, but the command did not produce test output and was interrupted after waiting.

### Patch check

```bash
git diff --check
```

Result:

- Pending after documentation update.

## Validation Summary

- No TypeScript, API-shape, import-path, or rendering mismatches were confirmed because frontend dependencies could not be installed in this network-restricted environment.
- Backend focused tests did not complete here because `uv` was blocked by environment/cache constraints.
- The remaining failures are environment-only and need registry access and a writable `uv`/pnpm setup to continue.
