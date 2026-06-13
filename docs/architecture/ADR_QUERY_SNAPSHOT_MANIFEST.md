# ADR: Query Snapshot Manifest

## Status

Accepted for the Stratum v0.6.0 runtime query observability milestone.

## Context

Query history preserves an execution snapshot, reconstruction describes how to
invoke it again, lineage describes its provenance, and verification compares a
historical result with a rebuilt result. A portable deterministic identity is
needed to summarize these contracts without copying their full structures.

## Decision

Stratum provides `QuerySnapshotManifestService` and:

`GET /queries/history/{execution_id}/manifest`

The service generates an on-demand `QuerySnapshotManifest` containing:

- execution, query version, and handler identity
- a canonical parameter hash
- a canonical result hash
- lineage and reconstruction contract versions
- a canonical content hash over those identities and references

Manifests are returned to callers and emitted in diagnostics. They are not
stored as authoritative records.

## Deterministic Identity

Hashing uses SHA-256 over canonical JSON:

- object keys are sorted
- separators are compact and stable
- non-finite numbers are rejected
- Pydantic models use JSON-compatible serialization
- list ordering remains meaningful
- volatile timestamp fields are excluded by default

Identical semantic inputs produce identical hashes regardless of dictionary
insertion order or manifest generation time.

## Hash Semantics

`parameter_hash` identifies the recorded reconstruction parameter snapshot.

`result_hash` identifies the historical or rebuilt result summary.

`content_hash` identifies the query execution contract envelope: execution,
query, handler, parameter and result hashes, lineage reference/version, and
reconstruction reference/version. `generated_at` is descriptive and excluded
from identity.

## Lineage Relationship

Manifest generation obtains lineage through `QueryLineageService`. The
manifest includes the lineage contract version and hashes a compact lineage
reference based on execution identity and version. It does not duplicate
source types, identifiers, counts, or authoritative source payloads.

## Verification Relationship

Query verification generates:

- `current_manifest` for the historical result
- `rebuilt_manifest` for the fresh deterministic result
- `hash_match` from their content hashes

Shared parameters and provenance retain the same hashes. Result drift changes
the rebuilt result hash and therefore the content hash. Manifest generation
failure does not overwrite history or convert derived data into authority.

## Diagnostics

Generation emits:

- `query_manifest_hash_computed`
- `query_manifest_generated`
- `query_manifest_generation_failed`

Diagnostics identify the execution, query, version, and content hash when one
was computed.

## Authority

The Event Store and Runtime Session State remain authoritative. Query
manifests, hashes, lineage, reconstruction information, verification results,
and diagnostics remain derived observability data.

No manifest creates a new source of truth, triggers execution, or mutates the
historical query record.
