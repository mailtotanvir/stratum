# ADR: Runtime Query Execution

## Status

Accepted for the Stratum v0.6.0 runtime query observability milestone.

## Context

The runtime query registry provides discovery and handler lookup. Query
execution also requires a consistent lifecycle for parameter validation,
execution identifiers, timing, result envelopes, and diagnostics.

Endpoints must not invoke query handlers directly.

## Decision

Stratum uses `RuntimeQueryExecutionService` as the only API execution pipeline.
The service:

1. resolves the handler and metadata through `RuntimeQueryRegistry`
2. validates parameters against the published query contract
3. emits an execution-started diagnostic
4. executes the handler once
5. records duration and success
6. emits completed or failed diagnostics
7. returns a common `RuntimeQueryExecutionResult`

Execution requests carry the query name, parameters, execution context, and
request timestamp. Execution results carry a unique execution identifier,
result data, diagnostics, and execution metadata.

## Validation Philosophy

Validation is strict and contract-driven:

- unknown parameters are rejected
- required parameters must be present
- values must already match their declared type
- values are not silently coerced
- all detected parameter issues are returned in a structured list

Handlers may retain domain validation, but transport-level parameter shape is
validated before handler invocation.

## Registry Architecture

The registry owns registration, lookup, and discovery metadata. The execution
service owns invocation. This keeps endpoints independent of concrete handlers
and preserves the same registry-driven extension pattern as projections.

## Execution Diagnostics

Execution emits:

- `runtime_query_execution_started`
- `runtime_query_execution_completed`
- `runtime_query_execution_failed`

Each diagnostic identifies the query, execution ID, duration, and success
state. The previous `runtime_query_executed` event remains as a compatibility
summary after successful execution.

## Determinism

Given unchanged authoritative state and identical validated parameters, handler
results must be deterministic. Execution IDs, timestamps, and measured duration
are operational metadata and are intentionally variable.

The execution service does not persist query results, mutate authoritative
state, trigger tools, or schedule future work.

## Authority

The Event Store and Runtime Session State remain canonical. Execution requests,
results, timing metadata, and diagnostics are request-scoped derived data.
