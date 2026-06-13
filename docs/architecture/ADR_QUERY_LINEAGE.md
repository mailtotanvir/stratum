# ADR: Query Lineage And Provenance

## Status

Accepted for the Stratum v0.6.0 runtime query observability milestone.

## Context

Query history identifies what ran and what result was observed.
Reconstruction identifies how the invocation can be rebuilt. Verification
determines whether a fresh result still matches. Operators also need
provenance: which authoritative records and identifiers contributed to the
historical execution context.

This is provenance, not memory.

## Decision

Stratum provides a registry-driven `QueryLineageService` and:

`GET /queries/history/{execution_id}/lineage`

The service:

1. loads the immutable history and reconstruction snapshots
2. resolves the current handler and metadata through `RuntimeQueryRegistry`
3. validates query version and handler identity
4. derives primary source type from the generic query type
5. discovers recorded `*_id` parameters
6. inspects Event Store events linked to those identifiers
7. discovers related identifiers and event source categories
8. returns deterministic source types, identifiers, and counts

Query names are not hardcoded. Session, decision, projection, and diagnostic
query types provide generic primary-source categories, while linked event
metadata supplies concrete provenance.

## Provenance Model

`QueryLineage` includes:

- execution, query, version, and handler identity
- the historical execution timestamp as deterministic generation context
- sorted source types
- concrete source identifiers such as session, event, and decision IDs
- source counts
- the complete reconstruction contract
- a versioned lineage contract

History records expose only a lineage endpoint reference. Authoritative source
payloads are not copied into history.

## Lineage Versus Reconstruction

Reconstruction describes how to invoke the query again: handler identity,
query version, execution timestamp, parameters, and reconstruction version.

Lineage describes which concrete source identifiers were associated with the
historical invocation context. Reconstruction is the path; lineage is the
provenance description.

## Lineage Versus Verification

Verification compares a historical result with one fresh deterministic
invocation. Lineage explains the source context independently of whether the
result verifies.

Verification responses include lineage when it can be generated. A lineage
generation failure does not replace or mutate the verification result.

## Read-Only Guarantee

Lineage generation never invokes a query handler, rebuilds a projection,
changes runtime state, or writes a lineage record. It emits only
`query_lineage_generated` or `query_lineage_generation_failed` diagnostics.

Repeated generation over unchanged history, registry metadata, and Event Store
state produces the same lineage output.

## Authority

The Event Store and Runtime Session State remain authoritative. Query results,
history, reconstruction information, verification results, lineage, and
lineage diagnostics remain derived observability data.

Lineage does not become a source of runtime facts and does not duplicate
authoritative payloads.

## Future Observability

Query lineage can support trace exploration, audit reports, source-impact
analysis, handler migration review, drift triage, dependency visualization,
and comparison with projection lineage. Future extensions must remain
registry-driven, explicit, read-only, and versioned.
