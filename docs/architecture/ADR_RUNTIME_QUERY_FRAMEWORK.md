# ADR: Runtime Query Framework

## Status

Accepted for the Stratum v0.6.0 runtime query observability milestone.

## Context

Runtime inspection currently requires callers to know individual projection,
session, decision, or diagnostic services. That couples consumers to storage
and derived-state implementation details.

Stratum needs a stable query layer for discovering and executing read-only
runtime questions without introducing a new source of truth.

## Decision

Stratum defines:

- `RuntimeQuery` as the versioned discovery contract
- `RuntimeQueryResult` as the common execution envelope
- `RuntimeQueryHandler` as the handler protocol
- `RuntimeQueryRegistry` as the runtime-owned registration and lookup service

Handlers publish parameter and result schemas. The registry validates unique
query names, exposes deterministic discovery metadata, executes handlers, and
emits common diagnostics.

## Registry Pattern

The query registry mirrors the projection registry:

- handlers are registered under stable names
- duplicate names fail fast
- lookup errors are predictable
- metadata can be discovered without executing the query
- callers execute through the registry rather than importing handlers

Registration itself does not create authority or persisted query results.

## Relationship To Projections

Queries may compose projections, authoritative services, or other read-only
derived services. Callers depend only on the query contract. A query handler
may change its internal composition while preserving its versioned external
schema.

The initial `session_decision_summary` query uses existing session, decision,
recommendation, and decision-trail services directly. It does not create a new
projection or require callers to understand projection models.

## Authority

The Event Store and Runtime Session State remain canonical. Query definitions,
metadata, results, and diagnostics are derived and request-scoped.

Executing a query does not mutate session state, persist a result, trigger
tools, or schedule work.

## Diagnostics

The framework emits:

- `runtime_query_registered`
- `runtime_query_discovered`
- `runtime_query_executed`

Diagnostics identify the query name, version, and handler.

## Future Observability

Future queries may expose projection health, session timelines, decision
analysis, and diagnostic summaries. Versioned contracts permit evolution
without coupling API consumers to database records or projection internals.
