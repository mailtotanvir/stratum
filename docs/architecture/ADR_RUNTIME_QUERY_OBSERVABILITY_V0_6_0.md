# ADR: Runtime Query Observability And Reconstruction v0.6.0

## Status

Accepted for the Stratum v0.6.0 runtime query observability milestone.

## Context

Stratum needs operator-facing observability without weakening the Runtime
Event Store as the authoritative record. Runtime queries, projections,
lineage views, reconstruction views, analytics, and intelligence summaries
must be rebuildable from event-store-backed evidence or existing runtime
records. They must not introduce memory systems, graph databases, LLM calls,
or external dependencies.

## Decision

The Runtime Event Store remains the source of truth for runtime activity,
diagnostics, projection lifecycle evidence, query execution diagnostics,
lineage reconstruction evidence, replay results, drift checks, analytics
diagnostics, and runtime intelligence diagnostics.

All v0.6.0 observability surfaces are derived query layers:

- runtime query discovery, execution, history, reconstruction, verification,
  lineage, manifests, and snapshot exports
- projection lifecycle, rebuild, replay, verification, manifests, lineage,
  snapshot exports, and drift detection
- governance audit projection
- decision lineage projection
- artifact lineage projection
- runtime reconstruction views
- runtime observability dashboard
- operational analytics
- runtime intelligence summaries
- explainability views
- projection registry v2 contracts
- provider and cost observability

These views may emit diagnostics about their own generation, but they do not
promote generated summaries, projections, analytics, intelligence, manifests,
exports, or reconstruction views to authoritative runtime state.

## Projection Model

Projection builders declare stable contracts and reconstruction metadata.
The projection registry stores contracts only. It does not persist projection
payloads, cache projection state, or execute builders except through explicit
service workflows.

Projection lifecycle records are reconstructed from `projection_rebuild_*`
events. Rebuilds are explicit operations and are recorded with source event
ranges and durations.

Projection replay derives request-scoped state from event-store evidence.
Replay preview is dry-run only. Replay completion emits replay diagnostics but
does not mutate authoritative runtime state.

Projection drift detection compares replay-derived fingerprints with current
rebuild fingerprints. Drift results are diagnostics and investigation signals,
not authoritative projection state.

## Governance And Lineage

The governance audit projection derives approval, rejection, policy,
reflection, and budget activity from runtime events. Governance summaries are
used by diagnostics, analytics, reconstruction, and intelligence, but remain
rebuildable.

Decision lineage and artifact lineage projections reconstruct relationships
from event metadata. Malformed or missing evidence is represented as
incomplete lineage rather than silently discarded. Incomplete lineage emits
diagnostics and is surfaced by reconstruction and intelligence summaries.

## Reconstruction Views

Runtime reconstruction views compose session state, event-store activity,
decision lineage, artifact lineage, governance audit evidence, tool activity,
and health signals. A reconstruction may be complete, incomplete, or failed.
Incomplete reconstruction preserves available data and records reasons.

Reconstruction views are request-scoped derived state. They do not repair,
rewrite, or replace authoritative records.

## Operational Analytics

Operational analytics aggregate event-store-backed runtime activity and
rebuildable projection summaries:

- session and event counts
- proposal, decision, artifact, and tool execution counts
- governance activity
- projection rebuild, replay, drift, and failure counts
- reconstruction completeness and duration summaries
- deterministic daily trend buckets

Analytics diagnostics are excluded from analytics source counts so reads do
not inflate their own metrics.

## Runtime Intelligence

Runtime intelligence summaries compose operational analytics, runtime health,
projection lifecycle state, reconstruction metrics, and high-signal runtime
events. They classify risks deterministically using stable risk identifiers.

Risk classification considers:

- critical runtime health issues
- projection drift
- failed reconstructions
- failed projection replays
- failed projection rebuilds
- governance rejection spikes
- incomplete lineage or reconstruction
- stale or missing projection rebuilds

Runtime intelligence diagnostics are excluded from intelligence source event
analysis so reads do not create self-reinforcing risks or activity.

## Explainability

Explainability views compose decision lineage, governance audit records,
artifact lineage, and runtime reconstruction data. They answer why a decision
was made, what evidence supported it, which recommendation or proposal was
selected, which artifacts resulted, and which governance actions influenced
the result.

Explanations tolerate incomplete history. Missing related evidence marks an
explanation incomplete with stable reasons instead of creating authoritative
repairs.

## Projection Registry v2

Projection Registry v2 formalizes projection contracts and capabilities for
projection and derived observability surfaces. It is a metadata and capability
registry, not an execution registry. The original builder registry remains the
source for rebuild, verification, replay, and drift execution.

Registry v2 enforces complete metadata, unique projection names, one active
version per projection name, and capability consistency. Capabilities identify
whether a projection is replayable, drift-checkable, reconstructable,
analyzable, or explainable.

## Provider And Cost Observability

Provider observability aggregates provider and model usage from runtime events
that carry provider/model metadata. It reports request counts, success and
failure counts, latency summaries, token estimates, and estimated costs when
those values are present.

Provider observability does not route providers, call provider APIs, call
billing APIs, or infer real invoice data. Missing token or cost metadata is
reported as unknown, not as a generation failure. Cost outputs are explicitly
marked as estimates.

## API Shape

v0.6.0 query and observability routes use explicit resource-oriented paths.
Some projection endpoints keep legacy aliases for backward compatibility,
while `/runtime/projections/...` remains the canonical runtime namespace.

Operator-facing summary endpoints return typed Pydantic models. Error paths
raise structured HTTP errors where source data is unavailable, malformed, or
inconsistent.

## Determinism

Derived views use deterministic ordering:

- event timelines sort by timestamp, event id, and event type
- lineage chains sort by stable timestamps and ids
- trend buckets sort by date
- risk summaries sort by severity and risk id
- projection registries and schemas sort by projection type

Malformed event timestamps are ignored for trend and recent-activity ordering
instead of failing the entire operator summary.

## Non-Goals

v0.6.0 does not introduce:

- persistent projection payload storage
- graph databases
- memory systems
- LLM-based summarization
- external analytics services
- automatic projection repair
- automatic governance remediation
- schema churn for historical runtime events
- provider routing or provider selection
- real billing reconciliation
- network calls to provider APIs

## Consequences

Operators gain compact summaries, reconstruction views, drift signals,
analytics, and risk intelligence while preserving the Event Store as the
audit source of truth.

Derived summaries can be regenerated and compared without mutating runtime
state. The cost is that some operator routes emit diagnostic events and must
explicitly exclude their own diagnostics from source counts to avoid feedback
loops.
