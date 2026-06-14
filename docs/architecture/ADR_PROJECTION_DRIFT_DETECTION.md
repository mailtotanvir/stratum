# ADR: Projection Drift Detection

## Status

Accepted for the Stratum v0.6.0 runtime query observability milestone.

## Context

Stratum has no authoritative or persisted projection payload store. Projection
builders produce request-scoped derived values, and replay analytics produce
ephemeral event-derived state. Drift detection must therefore avoid pretending
that current builder output or lifecycle metadata is persisted projection
state.

## Decision

The latest successful actual replay fingerprint is the persisted derived-state
baseline for drift analytics. `ProjectionDriftService` compares that baseline
to a fresh replay snapshot derived read-only from the Runtime Event Store.

Before a successful actual replay baseline exists, the projection reports
`unavailable`. It is not classified as in sync.

## Fingerprints

`projection_state_fingerprint` normalizes structured state, sorts mapping keys,
uses stable compact JSON, and computes SHA-256. Volatile timestamp fields such
as `built_at`, `generated_at`, and `verified_at` are excluded unless a future
caller explicitly models them as semantic data.

Replay state fingerprints include ordered applied event IDs, event types,
severity, messages, metadata, and event-type counts. This captures semantic
event changes while preserving deterministic ordering.

## Drift Status

- `in_sync`: the baseline and current replay fingerprints match
- `drifted`: the fingerprints differ
- `unavailable`: no successful actual replay baseline exists
- `failed`: current replay-derived state could not be produced

Mismatch summaries are deterministic operator-facing explanations rather than
full projection payloads.

## Diagnostics

Drift checks emit:

- `projection_drift_check_started`
- `projection_drift_check_completed`
- `projection_drift_detected`
- `projection_drift_check_failed`

These events are excluded from replay source selection. Repeated checks cannot
cause drift in their own inputs.

## Query Interfaces

`GET /runtime/projections/drift` checks all registered projections in registry
name order and isolates individual failures.

`GET /runtime/projections/{projection_name}/drift` checks one registered
projection.

## Safety And Authority

Drift checks do not invoke projection builders, rebuild projections, create
lifecycle records, or persist projection payloads. Replay snapshots are
request-scoped and discarded after fingerprinting.

The Runtime Event Store remains authoritative. Replay baselines, fingerprints,
and drift reports remain derived observability artifacts.
