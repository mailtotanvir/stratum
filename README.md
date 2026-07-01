# Stratum

Stratum is a local-first AI-assisted engineering runtime workstation.

It pairs a FastAPI backend with a desktop operator console so engineering work
can be executed, observed, governed, and replayed in a single local workflow.
The current v1.0 release candidate is a real milestone, but it is not a final
stable release.

## Release Status

Current RC validation status:

- Operator Console renders successfully.
- Backend validation currently has known RC stabilization failures.
- v1.0 RC is not final stable release yet.

The release candidate documentation is frozen in `docs/release/`, and the
latest validation notes are in `docs/validation/`.

## Project Summary

Stratum provides a governed runtime for local AI-assisted engineering work.
The backend records runtime history, execution events, approvals, artifacts,
and derived projections. The desktop console lets an operator inspect and
control that work over the local `localhost` boundary.

The design is intentionally event-first:

- the Runtime Event Store is the source of truth
- projections and summaries are derived, not authoritative
- provider choice is abstracted behind execution contracts
- agent execution is adapter-based rather than framework-bound
- the backend is the runtime authority, and the desktop is an operator client

## Why Stratum Exists

Stratum exists to make AI-assisted engineering work:

- local-first instead of cloud-dependent
- governed instead of opaque
- replayable instead of ephemeral
- provider-agnostic instead of tied to one model vendor
- agent-agnostic instead of tied to one framework

The goal is not just to run agents. The goal is to preserve a defensible record
of what happened, why it happened, and how it can be reconstructed later.

## Architecture Overview

Stratum is organized around an event-first runtime:

1. The Runtime Kernel schedules and coordinates execution.
2. The Runtime Event Store records authoritative history.
3. Runtime Sessions bind work to a governed execution context.
4. Workspace and Repository runtimes expose local engineering context.
5. Provider infrastructure isolates model and transport differences.
6. The execution participant layer keeps providers, agents, and participants
   independent from one another.
7. The Agent Marketplace and Skills layers provide extensibility without core
   lock-in.
8. Evaluations, artifacts, and projections are deterministic derived state.

The local boundary is simple:

- backend and source tree remain in WSL
- desktop communicates with the backend over `http://127.0.0.1:8000`
- real-time updates use HTTP and SSE on localhost
- no Windows source sync step is required

## Core Principles

- Event store first: the Runtime Event Store is authoritative.
- Derived state must be rebuildable from recorded events and artifacts.
- Provider, agent, and participant abstractions stay independent.
- The backend owns runtime authority; the desktop is a client.
- Local development should work without remote infrastructure.
- Validation matters more than feature claims in the RC phase.

## Current Capabilities

The current RC supports:

- local backend runtime and operator console
- session timeline, summaries, and replay-oriented views
- approvals and governance flows
- provider observability and execution diagnostics
- runtime reconstruction and query surfaces
- artifacts and lineage-tracked workspace changes
- adapter-based execution for agents and participant types

These capabilities are documented in the release guides and implemented in the
backend and desktop code already in the repository.

## Local Development Setup

The current supported local workflow is WSL-first.

### 1. Backend

From `backend/`:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Desktop

From `desktop/`:

```bash
pnpm install
pnpm dev
```

If you need a different API host for local testing, set:

```bash
VITE_RUNTIME_API_BASE_URL=http://127.0.0.1:8000 pnpm dev
```

### 3. Tauri shell

If the local checkout includes Tauri configuration:

```bash
pnpm tauri dev
```

## Backend Commands

From `backend/`:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Common validation patterns:

```bash
uv run pytest -q
uv run pytest tests/test_agent_loop_route.py tests/test_runtime_dashboard.py -q
```

## Desktop Commands

From `desktop/`:

```bash
pnpm install
pnpm dev
pnpm build
pnpm smoke
```

`pnpm smoke` runs the dependency-free console smoke check used to validate the
desktop shell navigation and console surfaces.

## Validation Commands

Repository-level validation is docs-driven in the RC, but the current practical
checks are:

```bash
cd backend && uv run pytest -q
cd backend && uv run pytest tests/test_agent_loop_route.py tests/test_runtime_dashboard.py tests/test_runtime_session_overview.py tests/test_runtime_timeline.py tests/test_runtime_status.py tests/test_provider_observability.py -q
cd desktop && pnpm smoke
scripts/runtime_console_smoke.sh
git diff --check
```

Validation notes:

- `scripts/runtime_console_smoke.sh` exercises the backend console path.
- `pnpm smoke` verifies the desktop shell navigation surfaces.
- `git diff --check` is the recommended docs/style sanity check for this repo
  when making README-only changes.

## WSL / Localhost Model

Stratum is set up for a WSL-backed local development model:

- the repository lives in WSL under `~/stratum`
- the backend runs in WSL
- the desktop connects to `127.0.0.1:8000`
- the runtime boundary is localhost-based, not sync-based
- no duplicate Windows checkout is required

This keeps the source of truth in one place and avoids introducing repository
mirroring or file-sync complexity.

## Provider / Agent / Participant Independence

Stratum separates the major execution roles so each one can evolve without
hard-coupling the others:

- providers handle model and transport differences
- agents are attached through adapter contracts
- participants are represented through the execution fabric, not hard-coded to
  one framework

This makes the runtime more stable across model changes, adapter changes, and
future extension work.

## Event Store As Source Of Truth

The Runtime Event Store is the authoritative record of runtime behavior.

That means:

- event history is primary
- projections are rebuildable views
- summaries are derived artifacts
- replay and reconstruction depend on recorded history, not UI state

If a projection becomes stale or inconsistent, it should be regenerated from the
event store and linked artifacts.

## Roadmap After v1

The v1.0 RC freezes the current platform surface. After v1, the documented
direction is to extend Stratum in measured ways rather than expand the core
without constraint.

The roadmap beyond v1 focuses on:

- broader provider coverage
- broader agent and adapter coverage
- richer observability and governance views
- stronger evaluation and reconstruction workflows
- safer extension points for third-party capabilities

## Future Vision

Future direction only: Stratum may evolve toward an observability, governance,
and intelligence layer for agentic runtimes, closer to a "Dynatrace/Elastic-
style" control plane for AI execution.

That is a future architectural direction, not a claim about the current RC.

## Known Limitations

- v1.0 RC is not a final stable release.
- Backend validation currently has known RC stabilization failures.
- Desktop screenshots and manual workflow evidence still require operator
  validation.
- Some API routes intentionally expose backward-compatible aliases.
- Live execution depends on provider configuration.
- No Windows source synchronization is used or required.

## Documentation Entry Points

- [Release Candidate Index](docs/release/STRATUM_V1_0_RC1.md)
- [Architecture Guide](docs/release/ARCHITECTURE_GUIDE.md)
- [Operator Guide](docs/release/OPERATOR_GUIDE.md)
- [Developer Guide](docs/release/DEVELOPER_GUIDE.md)
- [Known Limitations](docs/release/KNOWN_LIMITATIONS.md)
- [Roadmap Beyond v1](docs/release/ROADMAP_BEYOND_V1.md)
- [RC1 Validation Failure Log](docs/validation/RC1_VALIDATION_FAILURE_LOG_2026-06-30.md)
