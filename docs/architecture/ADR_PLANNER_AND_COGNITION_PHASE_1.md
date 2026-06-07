# ADR: Planner & Cognition Layer Phase 1

## Status

Accepted for Stratum v0.5.0 runtime work loop.

## Purpose

This ADR records the completed Phase 1 architecture for planning, recommendation
selection, decision auditability, proposal lineage, and cognition-related runtime
views.

Phase 1 provides deterministic planning and auditable decision support. It does
not make Stratum an autonomous agent.

## Scope

Phase 1 includes:

- `PlanningContext` as the canonical planner input view
- the `PlannerAdapter` boundary and deterministic `MockPlannerAdapter`
- `PlannerService`
- persisted planner recommendations and their lifecycle
- read-only recommendation selection preview
- explicit decision records
- explicit decision evidence
- proposal source lineage
- reconstructable decision trails
- derived cognitive state
- versioned planning-context snapshots
- event-backed reconstruction and diagnostics

## Architecture

The Phase 1 information flow is:

```text
Event Store
  -> Reconstruction
  -> Planning Context
  -> Planner
  -> Recommendation
  -> Selection Preview
  -> Decision Record
  -> Decision Evidence
  -> Proposal
  -> Decision Trail
  -> Cognitive State
```

The arrows describe information flow and lineage, not an autonomous execution
pipeline. Each mutating step still requires its explicit service or API call.

### Event Store and Reconstruction

The Runtime Event Store remains the authoritative source of truth for observed
runtime transitions and audit history. Reconstruction rebuilds lineage and
derived views from persisted events and records.

If a derived view becomes stale or its implementation changes, it must be
rebuildable without introducing a new source of truth.

### Planning Context

`PlanningContext` combines the current runtime session, active proposals, active
recommendations, available tools, recent events, and compact diagnostics. It is
derived state and is not persisted as a standalone record.

### Planner

`PlannerService` depends on the `PlannerAdapter` contract. Phase 1 uses
`MockPlannerAdapter`, which is deterministic and does not call an LLM or external
provider.

Planner output is advisory. It can create a recommendation record, but it cannot
execute work, approve a proposal, or promote a recommendation automatically.

### Recommendations and Selection

Planner recommendations are persisted audit records. Their lifecycle is:

- `active`
- `promoted`
- `dismissed`

Recommendation selection preview is a deterministic, read-only ranking view. It
does not create a decision, proposal, invocation, or execution.

### Decisions and Evidence

Decision records explicitly capture recommendation-selection decisions.
Decision evidence explicitly records the supporting recommendation, planning
context snapshot, governance preview, or another supported evidence reference.

Decision and evidence creation are separate, explicit audit writes. Phase 1 does
not infer or create evidence automatically.

### Proposals and Decision Trails

Proposals persist source lineage, including planner-recommendation sources.
Recommendation promotion to a proposal is explicit.

`DecisionTrail` is a derived reconstruction that connects:

```text
Proposal -> Recommendation -> Decision Record -> Decision Evidence
```

Incomplete lineage produces a partial trail and a diagnostic issue rather than
creating missing records.

### Cognitive State

`CognitiveState` is a derived, session-scoped summary of recommendation,
proposal, decision, evidence, tool-availability, and diagnostic state. It is a
read-only view and does not represent memory, hidden reasoning, or an execution
loop.

## State Ownership

The following are persisted audit records:

- planner recommendations
- proposals
- decision records
- decision evidence

The following are derived state:

- `PlanningContext`
- recommendation selection preview
- `DecisionTrail`
- `CognitiveState`
- reconstruction projections
- diagnostics summaries

Derived state must not become an independent authority. It may be recalculated
from persisted state and the Runtime Event Store.

## Snapshot Policy

Recommendation and proposal lineage may contain a compact `context_snapshot`.

Phase 1 snapshot rules are:

- `schema_version` is `1`
- snapshots contain compact audit evidence, not the full planning context
- snapshots are immutable historical context for lineage and diagnostics
- snapshots are not memory
- snapshots do not provide retrieval, learning, semantic search, or autonomous
  recall
- recommendation snapshots may be carried into proposal source lineage
- legacy or unknown snapshot versions remain visible to diagnostics

## Selection, Promotion, and Execution Policy

- selection preview is read-only
- decision records are created explicitly
- decision evidence is created explicitly
- recommendation promotion is explicit
- promotion may create a proposal but does not approve it
- proposal approval remains explicit
- proposal execution remains a separate runtime concern
- creating or reading planning and cognition records does not create tool
  invocations or execute tools

## Boundary Rules

Planner & Cognition Layer Phase 1 does not include:

- agent loops
- LLM planners
- memory systems
- embeddings
- ReAct
- autonomous execution
- automatic recommendation promotion
- automatic proposal approval
- hidden multi-step planning
- background decision creation

No Phase 1 read model or preview endpoint may cause proposal creation, tool
invocation, provider calls, or execution.

## Non-Goals

This ADR does not define:

- a general agent architecture
- chain-of-thought storage
- long-term or semantic memory
- automatic policy remediation
- autonomous proposal handling
- distributed runtime supervision
- an Event Fabric implementation

## Future Extension Points

Future capabilities may be added behind existing or new adapter contracts
without rewriting Phase 1 state ownership and lineage:

- `LLMPlannerAdapter`
- recommendation scoring adapters
- memory adapters
- multi-step planning adapters
- `BeamOtpRuntime` compatibility through the runtime adapter boundary

These are future options, not current behavior. Adding one requires a separate
architecture decision with explicit governance, determinism, audit, and
execution boundaries.

Event Fabric remains separate from Stratum core. It may integrate through stable
event interfaces in the future, but it must not replace Stratum's core domain
records, reconstruction contracts, or Runtime Event Store authority.

## Consequences

Phase 1 establishes a canonical, auditable planning and cognition layer while
preserving deterministic runtime behavior. Recommendations can be inspected,
selected, supported with evidence, promoted explicitly, and reconstructed
through proposal lineage.

The architecture leaves room for richer planner and runtime adapters without
turning the current system into an agent or coupling future capabilities to a
runtime rewrite.
