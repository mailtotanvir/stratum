# ADR: Runtime Health And Consistency

## Status

Accepted for the Stratum v0.6.0 runtime query observability milestone.

## Context

The observability dashboard summarizes runtime activity, but counts alone do
not answer whether the runtime is operationally healthy. Operators need stable
health signals that interpret consistency failures, failed rebuilds and query
executions, governance anomalies, and diagnostic severity.

## Decision

Stratum provides `RuntimeHealthService` and:

`GET /observability/health`

The service evaluates six read-only subsystems:

- runtime
- governance
- planner
- projections
- queries
- diagnostics

Each subsystem begins at 100 and receives fixed, bounded penalties for
persisted anomalies. Scores map to statuses:

- 90-100: `healthy`
- 75-89: `warning`
- 50-74: `degraded`
- 0-49: `unhealthy`

The overall score is the rounded arithmetic mean of subsystem scores. The same
unchanged inputs therefore produce the same status, score, and findings.

## Health Philosophy

Health is an interpretation of existing operational signals, not a new source
of facts. A finding identifies the signal type, severity, count, and operator
message. Subsystem diagnostics expose the counts used in scoring.

If one subsystem check cannot be completed, that subsystem returns an
unhealthy score of zero and emits `runtime_health_check_failed`. Other
subsystems remain available.

## Operational Signals

Runtime health checks session lifecycle integrity, task reconstruction
consistency, and Event Store accessibility.

Projection health reads rebuild, verification, and contract-validation failure
events. Query health reads execution, verification, and reconstruction-related
failure events.

Planner health uses recommendation lifecycle consistency and context snapshot
availability. Governance health uses proposal reconstruction consistency and
governance warning/error events. Diagnostics health uses warning, error, and
critical severities.

## Consistency Monitoring

Health evaluation does not trigger reconstruction, projection rebuild,
projection verification, query execution, or query verification. It calls
existing read-only consistency checks and inspects persisted events.

Health and dashboard lifecycle events are excluded from health source signals
so repeated reads do not degrade their own scores.

## Observability Versus Health

Observability reports what happened and exposes detailed artifacts. Health
assigns bounded operational meaning to those signals.

The dashboard includes only a compact health summary with overall status,
score, and subsystem status/score pairs. Detailed findings remain on the health
endpoint.

## Future Governance Applications

Health scores can support operator alerts, release gates, error-budget views,
and explicit governance policies. Any future enforcement must remain separate
from this read-only evaluation layer and must not convert health output into
authoritative runtime state.

## Authority

The Event Store and Runtime Session State remain authoritative. Health reports,
findings, scores, dashboard summaries, and evaluation diagnostics remain
derived request-scoped observability data.
