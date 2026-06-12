# ADR: Projection Snapshot Manifest

## Status

Accepted for the Stratum v0.5.0 runtime work loop.

## Context

Projection rebuild and verification produce derived, request-scoped output.
Operators need compact metadata describing what was produced, which builder and
schema were used, which authoritative session supplied the source, and whether
two outputs have the same normalized content.

## Decision

Stratum computes a `ProjectionSnapshotManifest` for projection output. A
manifest records:

- projection name, schema version, and builder name
- generation time
- source session and session-linked source event count
- runtime identifier when a distinct runtime identifier exists
- reconstruction information
- optional verification status
- deterministic SHA-256 content hash

The current runtime model has no runtime identifier distinct from task/session
identity, so `source_runtime_id` is currently null.

## Deterministic Hashing

Projection content is normalized to JSON-compatible data, object keys are
sorted, and compact JSON encoding is hashed with SHA-256. List order remains
significant.

Volatile timestamps such as `built_at`, `generated_at`, and `verified_at` are
excluded by default. Callers may explicitly include volatile fields when using
the hashing utility directly.

## Authority

Manifests are derived metadata. Their hashes are verification aids, not proof
of authority and not replacements for source events or session records. The
Event Store and Runtime Session State remain canonical.

Manifest generation does not persist projection payloads, create snapshot
authority, mutate projection state, or trigger execution.

## Rebuild And Verification

Rebuild responses include a manifest for rebuilt projection data. Verification
responses include current and rebuilt manifests plus `hash_match`. Field-level
verification remains the detailed drift diagnostic; hash equality is a compact
consistency signal.

## Source Event Count

`source_event_count` includes persisted events explicitly linked to the source
session. Projection build, rebuild, verification, and manifest diagnostics are
excluded so observing a projection cannot change the authoritative source count
reported by its manifest.

## Future Use

Manifests support drift detection, replay diagnostics, and future explicit
snapshot export. Future governance may sign, retain, or compare manifests, but
must preserve their derived status and keep execution operator-controlled.
