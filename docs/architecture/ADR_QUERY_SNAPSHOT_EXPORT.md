# ADR: Query Snapshot Export

## Status

Accepted for the Stratum v0.6.0 runtime query observability milestone.

## Context

Query history, reconstruction, lineage, manifests, and verification provide
separate observability views. Operators need one portable artifact that groups
those views for inspection, audit, and offline analysis without creating a new
runtime source of truth.

## Decision

Stratum provides `QuerySnapshotExportService` and:

`POST /queries/history/{execution_id}/export`

An export contains:

- the immutable query execution record
- reconstruction metadata
- on-demand lineage
- the deterministic snapshot manifest and its hashes
- the latest recorded verification status, when available
- export lifecycle diagnostics

The service never invokes a query handler and never performs verification.

## Observability Artifact Model

Exports are request-scoped diagnostic artifacts. They compose existing derived
contracts rather than copying authoritative runtime records beyond the
historical query result already retained in query history.

The verification status is read from the latest
`query_verification_completed` event for the execution. It contains the
verified state and difference count. If no prior verification exists, the
status is absent.

## Deterministic Export Requirements

For unchanged Event Store, query history, registry metadata, and runtime
session state, all export content is deterministic except:

- `export_id`
- `exported_at`

The embedded manifest uses the historical execution timestamp as
`generated_at`, preventing request time from changing portable content.
Diagnostics vary only by export identifier.

No environment paths, process details, host identifiers, or hidden runtime
fields are included.

## Lineage Relationship

Lineage is generated on demand and included directly in the artifact. It
describes source categories and identifiers without duplicating authoritative
payloads or persisting a lineage record.

## Manifest Relationship

The export includes parameter, result, and content hashes from
`QuerySnapshotManifest`. The content hash supplies a compact deterministic
identity for the execution snapshot and its reconstruction and lineage
contract versions.

## Diagnostics

Export emits:

- `query_snapshot_export_started`
- `query_snapshot_export_completed`
- `query_snapshot_export_failed`

Diagnostics include execution identity, query version, export identifier, and
the manifest content hash when available.

## Authority

The Event Store and Runtime Session State remain authoritative. Query exports,
history, reconstruction metadata, lineage, manifests, verification status, and
diagnostics remain derived observability data.

Exports are not persisted, do not mutate history, do not execute queries, and
do not introduce a new authoritative state boundary.
