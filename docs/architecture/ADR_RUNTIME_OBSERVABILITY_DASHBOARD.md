# ADR: Runtime Observability Dashboard

## Status

Accepted for the Stratum v0.6.0 runtime query observability milestone.

## Context

Stratum exposes detailed runtime events, diagnostics, projections, query
history, verification, lineage, manifests, and exports. Those artifacts are
appropriate for investigation but require operators to assemble basic runtime
health and activity questions manually.

## Decision

Stratum provides `RuntimeDashboardService` and:

`GET /observability/dashboard`

The service returns seven versioned, operator-facing sections:

- runtime
- sessions
- decisions and recommendations
- projections
- queries
- governance
- diagnostics

Each section has a stable name and version, a shared generation timestamp,
summary content, and metadata identifying it as derived and listing its source
services.

## Dashboard Philosophy

The dashboard is a compact aggregation layer. It answers operational questions
such as how many sessions are active, which projections and queries are
registered, how often rebuild and verification paths run, and whether recent
events indicate governance or diagnostic issues.

It does not replace detailed endpoints. Operators can move from dashboard
counts to projection, query, event, lineage, manifest, or export APIs for
investigation.

## Aggregation Versus Authority

Dashboard generation reads existing service records, registries, and persisted
events. It does not create sessions, decisions, recommendations, proposals,
projections, query executions, verification results, or exports.

The dashboard response is request-scoped derived data. The Event Store and
Runtime Session State remain authoritative.

Dashboard lifecycle diagnostics are excluded from dashboard event counts so
reading the dashboard does not inflate its own operational metrics.

## Relationship To Projections

The projection section reports registered projection contracts and counts
completed rebuild and verification operations from the Event Store. It does
not build, rebuild, verify, or persist any projection.

## Relationship To Queries

The query section reports registered query contracts and counts completed
executions and verifications. Registry inspection uses a non-emitting name
lookup and never invokes a query handler.

## Operator-Facing Model

The dashboard favors bounded counts, statuses, registered names, and recent
diagnostic event summaries. It omits full authoritative payloads and detailed
derived artifacts.

Generation emits `runtime_dashboard_generated` or
`runtime_dashboard_generation_failed` with generation duration and section
count. These events provide observability for the aggregation layer without
promoting the dashboard to authoritative state.
