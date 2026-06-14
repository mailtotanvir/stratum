# ADR: Governance Audit Trail Projection

## Status

Accepted for the Stratum v0.6.0 runtime query observability milestone.

## Context

Governance activity is distributed across runtime policy decisions, tool
execution policy decisions, recommendation selection, decision records,
proposal resolution, error-budget consequences, and reflection lifecycle
events. Operators need one deterministic audit view without introducing a new
authoritative governance store.

## Decision

Stratum registers `governance_audit_projection` and provides
`GovernanceAuditProjectionBuilder`. The builder consumes persisted Runtime
Event Store events and derives typed `GovernanceAuditRecord` values.

The projection includes:

- runtime and tool policy evaluations
- recommendation promotions and dismissals
- decision record selections
- proposal approvals and rejections
- reflection requests and resolutions
- budget references when governance reasons identify budget enforcement

Unrelated runtime events and decision evidence events are not separate audit
records. Decision evidence events contribute evidence counts to their decision
records.

## Event Validation

Each governance event type has required identity and outcome metadata. Missing
identifiers, missing outcomes, or invalid proposal terminal statuses raise
`GovernanceAuditProjectionBuildError`. The builder does not invent incomplete
audit facts.

## Ordering

The canonical projection stores records oldest first by occurrence timestamp,
source event ID, and decision ID. Query responses reverse that canonical order
and return newest first. Equal inputs therefore produce equal record order.

## Diagnostics

Explicit projection builds and framework rebuilds emit:

- `governance_decision_recorded`
- `governance_projection_updated`
- `governance_projection_rebuilt`

Read-only audit and summary queries use `build_read_only` and do not emit these
events. Projection diagnostics are excluded from projection source-event
analytics.

## Query Interfaces

- `GET /runtime/governance/audit`
- `GET /runtime/governance/audit/{decision_id}`
- `GET /runtime/governance/summary`

The summary includes decision counts and the requested observability metric
names for records, approvals, rejections, policy evaluations, reflection
triggers, and budget actions.

## Authority

The Runtime Event Store remains authoritative. The governance audit projection,
records, summaries, and metrics are derived and rebuildable. Querying or
rebuilding the projection does not mutate governance decisions, proposals,
recommendations, lifecycle state, or runtime policy.
