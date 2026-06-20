# ADR: Governance Intelligence Layer

## Status

Accepted for the Stratum v0.7.0 governance intelligence layer milestone.

## Context

Stratum needs governance intelligence that explains whether runtime decisions,
planner recommendations, policies, and evaluated outcomes are producing useful
results. Operators need rollups and drill-down views, but those views must not
become a learning system, a policy automation loop, or a second source of
truth.

Earlier milestones established the Runtime Event Store and projection
framework as the foundation for deterministic, rebuildable runtime views.
v0.7.0 extends that model with evaluation-backed governance intelligence.

## Decision

Stratum introduces a Governance Intelligence Layer composed of source
evaluation records and rebuildable projections. The layer answers governance
quality questions from existing runtime evidence without changing runtime,
planner, policy, or recommendation behavior.

The layer includes:

- `EvaluationRecord`
- `EvaluationSummaryProjection`
- `EvaluationOutcomeRollupProjection`
- `EvaluationTrendProjection`
- `PolicyEvaluationOverviewProjection`
- `RecommendationOutcomeProjection`
- `DecisionEffectivenessProjection`
- `GovernanceHealthRollupProjection`
- query catalog, manifest, and executor integration for the registered
  intelligence surfaces

## EvaluationRecord As Source Data

`EvaluationRecord` is the source data for evaluated outcomes because it records
explicit assessment facts:

- what target was evaluated
- which target id was evaluated
- which evaluation type was used
- what outcome was observed
- optional score, evaluator, rationale, and metadata

Evaluation records are runtime evidence. They are not projections and they are
not inferred from projection payloads. Projections may summarize them, group
them, or connect them to related runtime records, but the evaluation record is
the canonical evaluation fact.

This boundary lets Stratum add manual evaluation workflows, benchmark
evaluations, provider comparisons, or other evaluation producers later without
changing projection semantics.

## Projection State

Governance intelligence projections remain derived, disposable, and
rebuildable. They do not own authoritative state.

Each projection builder creates fresh typed projection data from existing
runtime records. Rebuilding a projection does not:

- mutate runtime sessions
- alter planner recommendations
- change recommendation selection
- update policies
- tune thresholds
- create new evaluations
- persist projection payloads as authority

Projection metadata declares the projection type, schema version, builder, and
reconstruction source. That metadata documents how the projection can be
recreated and keeps the projection aligned with the broader projection
framework.

## Relationship To Event Store And Projection Architecture

The Runtime Event Store remains authoritative for event-backed runtime history.
Runtime services and records remain authoritative for their own durable facts.
Governance intelligence follows the same architecture:

- source records capture explicit facts
- projection builders derive request-scoped views
- registry metadata exposes contracts and capabilities
- rebuild, replay, drift, manifest, and verification services operate on
  projection contracts
- query surfaces expose typed read models

The Governance Intelligence Layer does not replace the Event Store. It adds
evaluation-oriented views over runtime and governance evidence.

## Governance Intelligence Surfaces

### Evaluation Summary

`EvaluationSummaryProjection` summarizes evaluation records for filtered target
types, target ids, evaluation types, and outcomes. It is the direct
evaluation-record summary surface.

### Outcome Rollup

`EvaluationOutcomeRollupProjection` aggregates outcome counts and rates across
evaluation records. It provides the base answer to whether evaluated outcomes
are mostly successful, failing, accepted, rejected, reverted, or inconclusive.

### Evaluation Trend

`EvaluationTrendProjection` buckets evaluation outcomes over deterministic time
windows. It supports questions about whether outcomes are improving or
degrading over time without adding forecasting or learning.

### Policy Evaluation Overview

`PolicyEvaluationOverviewProjection` connects policies to linked evaluation
records through policy decisions and violations. It answers which policies are
associated with successful, failed, accepted, rejected, reverted, or
inconclusive outcomes.

### Recommendation Outcome

`RecommendationOutcomeProjection` connects planner recommendations to
selection records and recommendation-targeted evaluations. It answers which
recommendations are selected, rejected, evaluated, and associated with
successful or unsuccessful outcomes.

This projection does not rank recommendations and does not feed results back
into planner behavior.

### Decision Effectiveness

`DecisionEffectivenessProjection` connects recorded runtime decisions to
decision-targeted evaluations. It answers which decisions have evaluation
coverage, which outcomes are associated with each decision, and the average
evaluation score per decision.

This projection does not modify decision records and does not infer that a
decision should have been different.

### Governance Health Rollup

`GovernanceHealthRollupProjection` summarizes the top-level health of the
governance layer across evaluation, policy, recommendation, and decision
effectiveness surfaces.

The rollup uses deterministic status rules:

- `unknown` when no evaluation data exists
- `healthy` when overall success rate is at least `0.8` and reversion rate is
  at most `0.05`
- `watch` when overall success rate is at least `0.6`
- `degraded` otherwise

Health reasons explain the selected status. The rollup is an operator signal,
not an automated remediation trigger.

## Query Integration

Governance intelligence projections participate in the runtime query catalog,
manifest, and executor pattern established by runtime query observability.

The catalog exposes projection names, routes, categories, filters, and
rebuildability metadata. The manifest composes catalog entries and health
metadata into a portable query inventory. The executor dispatches supported
query ids to read-only projection builders.

Query integration provides discovery and a consistent execution surface. It
does not persist query results as authority and does not schedule background
projection work.

## Determinism

Governance intelligence views must be deterministic:

- equal source records produce equal projection content except build timestamps
- missing evaluations produce zero counts and stable coverage flags
- orphan evaluation references are ignored deterministically
- sorting uses stable identifiers and counts
- empty state returns explicit zero values and `unknown` health where
  applicable

This keeps governance intelligence suitable for rebuild, replay, verification,
snapshot export, and drift investigation.

## Non-Goals

v0.7.0 Governance Intelligence does not introduce:

- a learning system
- autonomous optimization
- policy auto-tuning
- recommendation ranking
- embeddings
- memory
- an LLM evaluator
- automatic policy remediation
- automatic planner behavior changes
- automatic recommendation selection changes
- background governance feedback loops
- external analytics services

Governance intelligence is observational and deterministic. It reports what
the recorded evidence says; it does not decide what the runtime should do
next.

## Consequences

Operators gain a coherent governance intelligence layer that connects
evaluations to policies, recommendations, decisions, and top-level health.

The architecture preserves Stratum's runtime-first model:

- source records remain explicit
- projections remain rebuildable
- query surfaces remain read-only
- runtime behavior remains unchanged
- governance automation remains out of scope

The cost is that richer governance answers require explicit evaluation
coverage. Missing evaluations are surfaced as missing coverage rather than
being inferred.

## Future Extensions

Future milestones may add:

- manual evaluation workflows
- provider and model outcome comparisons
- benchmark suites
- UI governance dashboards
- milestone-level release health
- richer evaluator provenance and review flows
- comparative views across sessions, tasks, providers, and policies

Any future extension must preserve the boundary between source records,
derived projections, and runtime behavior. Automated optimization, learning,
or policy tuning would require a separate architecture decision.
