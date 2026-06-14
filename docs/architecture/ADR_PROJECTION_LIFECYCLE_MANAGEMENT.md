# ADR: Projection Lifecycle Management

## Status

Accepted for the Stratum v0.6.0 runtime query observability milestone.

## Context

Projection rebuild diagnostics identify that a rebuild started, completed, or
failed, but previously did not provide a complete operational record. Runtime
operators need projection versions, rebuild timestamps, source event ranges,
durations, current status, and deterministic history without making projection
outputs authoritative.

## Decision

Stratum provides `ProjectionLifecycleService`. The service registers lifecycle
transitions through the existing projection rebuild events:

- `projection_rebuild_started`
- `projection_rebuild_completed`
- `projection_rebuild_failed`

The start event is the correlation anchor. Terminal events reference its event
ID and contain a completed `ProjectionRebuildRecord`. Lifecycle history is
reconstructed from the Runtime Event Store and ordered by rebuild start time,
then start event ID, newest first.

No lifecycle database or projection payload store is introduced.

## Lifecycle Record

Each record contains:

- projection name and schema version
- rebuild start and completion timestamps
- started, completed, or failed status
- source event count
- first and last source event IDs
- duration in milliseconds

Source events use the same exclusion policy as projection snapshot manifests.
This keeps manifest counts and lifecycle ranges consistent and excludes
projection/query observability events from authoritative rebuild inputs.

## Query Interfaces

`GET /runtime/projections` retains the existing `projection_types` and
`schemas` fields and adds a `projections` status table. Each row includes the
registered version and latest rebuild status, timestamps, and duration.

`GET /runtime/projections/history` returns typed rebuild records ordered newest
first. These records directly support a rebuild history table and duration
trend chart without requiring projection payloads.

Both lifecycle queries are read-only. They do not build projections or emit
lifecycle events.

## Failure Semantics

A rebuild that fails contract validation or execution receives a terminal
failed record. A start event without a terminal event remains visible with
`started` status, allowing interrupted rebuilds to be observed.

Legacy rebuild events without enriched lifecycle fields are reconstructed from
their event timestamps and existing projection metadata where possible.

## Authority And Boundaries

The Runtime Event Store remains authoritative for lifecycle facts. Projection
payloads remain derived, disposable, and rebuildable. Lifecycle status and
history are derived query models and cannot become inputs to projection
builders or runtime execution.

The registry remains responsible only for projection contracts and discovery.
The rebuild service orchestrates explicit rebuilds. The lifecycle service owns
rebuild event registration and read-only history reconstruction.

## Consequences

- Rebuild observability is durable through the existing Event Store.
- Projection status is deterministic and reconstructable.
- Existing discovery fields remain backward compatible.
- No automatic rebuilds, scheduling, autonomous loops, or external
  infrastructure are introduced.
