# ADR: Projection Snapshot Export

## Status

Accepted for the Stratum v0.5.0 runtime work loop.

## Context

Projection rebuilds and manifests provide request-scoped diagnostic data.
Operators also need a portable API object that groups canonical projection
content, its manifest, and reconstruction metadata for external inspection.

## Decision

Stratum provides an explicit projection snapshot export service and endpoint.
The service:

1. resolves the projection contract through `ProjectionRegistry`
2. rebuilds through `ProjectionRebuildService`
3. includes the generated snapshot manifest
4. includes reconstruction metadata
5. optionally performs projection verification
6. returns a `ProjectionSnapshotExport` object

No file is written. Persistence and transport formats beyond the API response
are intentionally deferred.

## Determinism

Exported projection content uses canonical projection serialization and excludes
volatile projection timestamps. The exported manifest retains the deterministic
content hash and anchors its generation timestamp to the source session.

For unchanged authoritative inputs, export content is stable except for
`export_id`, `exported_at`, and diagnostic references to the export identifier.

## Authority

Exports are diagnostic artifacts, not authoritative runtime state. Exporting a
projection does not persist projection payloads, mutate session state, replay
events, or execute work.

The Event Store and Runtime Session State remain canonical. Snapshot manifests,
hashes, verification results, and exports remain derived metadata.

## Diagnostics

Export emits:

- `projection_snapshot_export_started`
- `projection_snapshot_export_completed`
- `projection_snapshot_export_failed`

Diagnostics identify the projection, export, schema version, builder, and
content hash when available.

## Future Use

Portable exports can support bug reports, replay debugging, and regression
fixtures. Future file persistence, signing, compression, or upload behavior
requires a separate explicit design and must not create projection authority or
automatic execution.
