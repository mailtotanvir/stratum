# ADR: Query Verification And Drift Detection

## Status

Accepted for the Stratum v0.6.0 runtime query observability milestone.

## Context

Query history records what a versioned query returned for a parameter snapshot
at a specific time. Authoritative runtime state, query handlers, schemas, and
reconstruction contracts may later change. Operators need an explicit way to
determine whether the historical result can still be reproduced.

## Decision

Stratum provides `QueryVerificationService` and:

`POST /queries/history/{execution_id}/verify`

Verification:

1. loads the immutable historical execution and reconstruction snapshot
2. validates reconstruction metadata against the history record
3. resolves the current handler and query contract through the registry
4. requires the current query version to match the historical version
5. rebuilds the request from the historical parameter snapshot
6. invokes the handler once
7. compares the fresh result with the historical result summary
8. returns deterministic field-level differences

The normal execution service is deliberately not used. Verification therefore
does not create another history record or present verification as an ordinary
query execution.

## Query Drift

Query drift means that a fresh deterministic invocation no longer matches the
historical result. Drift may result from:

- changed authoritative Event Store or Runtime Session State
- changed handler behavior
- changed result shape
- changed handler identity
- changed reconstruction behavior

A query version mismatch is a verification precondition failure rather than a
result difference. It requires explicit version-aware migration or analysis.

## Difference Model

Verification reports stable, path-sorted differences:

- `missing_field`
- `unexpected_field`
- `value_mismatch`
- `metadata_mismatch`
- `result_summary_mismatch`

Handler identity drift is metadata drift. Root scalar or incompatible summary
values use `result_summary_mismatch`.

## Verification Philosophy

Verification is explicit and operator-triggered. It performs one read-only
handler invocation using the recorded parameters. It does not schedule work,
retry, repair, update state, or automatically accept a rebuilt result.

Unknown executions, missing handlers, query version mismatches, incomplete
reconstruction metadata, invalid historical parameters, and handler failures
produce predictable failures with diagnostics.

## No Mutation Guarantee

The historical `query_history_recorded` event is never changed or replaced.
The fresh result exists only in the verification response. Verification emits
its own diagnostic events but does not append another history record.

## Authority

The Event Store and Runtime Session State remain authoritative. Query history,
reconstruction information, fresh verification results, differences, and
verification diagnostics remain derived observability data.

No verification output becomes authoritative runtime state.

## Relationship To Projection Verification

Projection verification compares a current derived projection with an explicit
rebuild from the same authoritative source. Query verification compares an
immutable historical query result with a fresh invocation reconstructed from
the historical query contract.

Both use deterministic field-level differences and preserve authoritative
boundaries. Query verification additionally validates handler identity, query
version, and historical parameter reconstruction.
