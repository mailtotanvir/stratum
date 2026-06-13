# ADR: Query History And Reconstruction

## Status

Accepted for the Stratum v0.6.0 runtime query observability milestone.

## Context

Runtime query execution already provides registry-driven discovery, strict
parameter validation, execution identifiers, result envelopes, and lifecycle
diagnostics. Operators also need to inspect what ran and retain enough metadata
to analyze or verify an execution later.

Query history must not become a second source of runtime truth, and history
inspection must never execute a query.

## Decision

Each known-query execution produces a `QueryExecutionRecord` containing its
execution identifier, versioned query identity, timestamp, parameter snapshot,
execution metadata, success state, and result summary.

`QueryHistoryService` stores no independent records. It writes the immutable
diagnostic snapshot to the existing Event Store as a
`query_history_recorded` event and derives history by reading those events.
The service exposes list and detail views through:

- `GET /queries/history`
- `GET /queries/history/{execution_id}`

Successful executions record the returned result as the result summary. Failed
known-query executions record structured error information. An unknown query
cannot produce a versioned record because no registered query contract exists.

## Query Execution Lifecycle

1. The execution service assigns an execution identifier.
2. The registry resolves the handler and immutable query metadata.
3. Parameters are validated.
4. The handler executes at most once.
5. Execution completion or failure diagnostics are emitted.
6. A diagnostic history snapshot is appended to the Event Store.
7. Reconstruction metadata is generated without invoking the handler.

## History Philosophy

History is an observability view over persisted diagnostic events. It is
append-only, inspectable, and reconstructable from the existing Event Store.
There is no query-history table, repository, cache, memory system, or other
source of truth.

The history record captures the result observed at execution time. It does not
claim that the same result would be produced against later runtime state.

## Reconstruction Philosophy

`QueryReconstructionInfo` contains:

- query name and version
- handler name
- original execution timestamp
- an immutable parameter snapshot
- reconstruction contract version

For a fixed execution record, reconstruction information is deterministic.
It supports replay analysis, diagnostics, and verification tooling, but this
sprint performs no replay and no automatic re-execution.

## Authority

The Event Store and Runtime Session State remain authoritative. Query
definitions, execution records, result summaries, reconstruction metadata, and
history responses are derived diagnostic data.

Persisting a history diagnostic does not promote its result to domain state.
Deleting or rebuilding a derived history view does not alter the underlying
runtime session or domain facts.

## Observability

The lifecycle emits:

- `query_history_recorded`
- `query_history_retrieved`
- `query_reconstruction_generated`

Each diagnostic includes the execution ID, query name, and query version.
These events permit operators to trace history creation and inspection while
preserving the boundary between observation and execution.
