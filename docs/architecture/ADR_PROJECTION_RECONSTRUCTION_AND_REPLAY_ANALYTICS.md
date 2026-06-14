# ADR: Projection Reconstruction And Replay Analytics

## Status

Accepted for the Stratum v0.6.0 runtime query observability milestone.

## Context

Projection rebuilds operate from current reconstruction services. Operators
also need to understand how persisted Runtime Event Store history contributes
to registered projections, including bounded event ranges and dry-run analysis.

Calling existing builders for a bounded event range would be misleading:
builders read current runtime services and are not event-stream consumers.
Replay therefore requires a separate event application boundary.

## Decision

Stratum provides `ProjectionReplayService`. It reads persisted runtime events,
orders them deterministically by event ID, timestamp, and event type, and
applies relevant events through a projection-specific replay adapter.

Replay state is request-scoped and in memory. It is never written as
authoritative or persisted projection state.

The initial adapters support:

- `decision_projection`
- `session_decision_projection`

Both consume recommendation lifecycle, decision record, decision evidence, and
proposal lifecycle events. Other selected runtime events are counted as
skipped. A registered projection without a specialized adapter uses the
generic all-source-events adapter, preserving deterministic replay and drift
support until a narrower projection-specific policy is registered.

## Replay Modes

Full replay selects all projection source events from the Runtime Event Store.
Bounded replay applies inclusive `event_id_start` and `event_id_end` filters.

Dry-run replay executes the same event selection, ordering, applicability, and
validation path but does not retain materialized replay state. Actual replay
completes an ephemeral materialization pass and then discards it because
Stratum has no persisted projection store.

This distinction supports future derived projection stores without making one
part of the current architecture.

## Result Model

Each result reports projection identity and version, timestamps, completion or
failure status, selected/applied/skipped/failed event counts, duration, and
dry-run mode. Results contain analytics only, not projection payloads.

## Diagnostics

Replay emits:

- `projection_replay_started`
- `projection_replay_completed`
- `projection_replay_failed`
- `projection_replay_dry_run_completed`

Replay diagnostics are excluded from later projection source selection. A
repeated replay over unchanged authoritative events therefore produces the
same event counts and ordering.

## Failure Safety

Adapters apply events only to request-scoped state. If an adapter fails, the
service stops, emits a failed diagnostic, and returns failure analytics through
`ProjectionReplayError`. Existing projections and authoritative state cannot
be partially updated or corrupted.

## Query Interfaces

`GET /runtime/projections/replay/preview` performs dry-run analytics.

`POST /runtime/projections/replay` performs the ephemeral replay pass.

Both accept a projection name and optional inclusive event ID bounds.

## Authority

The Runtime Event Store remains the replay source of truth. Replay analytics,
adapter state, and results are derived and disposable. Replay does not invoke
agents, planners, autonomous loops, external infrastructure, or automatic
execution.
