# ADR: Planner & Cognition Layer Phase 2

## Status

Accepted for Stratum v0.5.0 runtime work loop.

## Context

Planner & Cognition Phase 1 introduced deterministic planning, persisted
recommendations, read-only recommendation selection, derived planning context,
and derived cognitive state.

Phase 2 tightens planner input construction so production callers cannot provide
derived planner state as authoritative input. It also makes canonical input
construction observable and exposes lightweight version metadata without
persisting cognition payloads or changing planner execution semantics.

## Decision

`PlannerInputBuilderService` is the canonical production boundary for creating
`PlannerRequest`.

Runtime, session, planner, and recommendation-selection preview flows provide a
runtime session identifier and objective to the builder. The builder derives
the planner request from current authoritative session and Event Store state.
Production callers must not construct or inject `PlanningContext`,
`CognitiveState`, or planner snapshot metadata directly.

Direct `PlannerRequest` construction remains available for model, adapter,
service-boundary, persistence, and compatibility tests.

## Canonical Input Construction

For each build, `PlannerInputBuilderService`:

1. loads the runtime session
2. rebuilds `PlanningContext`
3. rebuilds `CognitiveState` from that planning context
4. loads and deterministically orders enabled planner tools
5. creates fresh planner input snapshot metadata
6. emits a safe `planner_input_built` diagnostic event
7. returns the canonical `PlannerRequest`

Repeated builds against unchanged authoritative state produce equivalent
planning context, cognitive state, tools, and recommendation summaries. Derived
objects and build timestamps are recreated for each build.

## Planner Request

### Cognitive State

`PlannerRequest.cognitive_state` contains the derived, session-scoped
`CognitiveState`.

It summarizes recommendation, proposal, decision, evidence, tool-availability,
and diagnostic state. It is advisory input for planner inspection and event
summaries. It is not memory, hidden reasoning, persisted authority, or an
execution control.

### Snapshot Metadata

`PlannerRequest.snapshot_metadata` contains
`PlannerInputSnapshotMetadata`:

- `session_id`
- `planner_context_snapshot_version`
- `cognitive_state_snapshot_version`, when defined
- `built_at`
- `source`, currently `planner_input_builder`

Snapshot metadata identifies the derived input contract received by a caller.
It is rebuilt on every canonical input build and does not replace or mutate
session state.

`PlannerService` may read snapshot metadata for observational event fields. Its
planning behavior must not depend on the metadata.

## Planner Input Diagnostics

Every canonical build emits `planner_input_built`.

The event contains safe summary metadata derived from planner input snapshot
metadata, plus bounded counts such as available recommendations and tools. It
must not contain full `PlanningContext` or `CognitiveState` payloads.

The diagnostic is observational only. Emitting it does not make it an input to
the same planner build, mutate session state, change recommendation ranking, or
trigger execution.

## Recommendation Selection Preview

Recommendation selection preview builds canonical planner input to obtain
snapshot metadata. Its response may expose:

- `planner_context_snapshot_version`
- `cognitive_state_snapshot_version`, when defined
- `planner_input_source`

The response does not expose full planning context or cognitive state.

Selection ranking remains deterministic and based on persisted active
recommendation records. The preview does not invoke `PlannerService`, create
recommendations or proposals, mutate recommendation status, create tool
invocations, or execute work.

## State Ownership

The Runtime Event Store and persisted session/domain records remain the source
of truth.

`PlanningContext` and `CognitiveState` are derived and rebuildable projections.
Planner input snapshot metadata describes a particular build of those
projections; it does not make the projections authoritative.

If derived state becomes stale or its implementation changes, it must be
rebuildable from authoritative state without requiring previously emitted
planner input diagnostics.

## Consequences

- production planner callers share one canonical input-construction path
- caller-provided planner context cannot override authoritative session state
- planner input contracts are inspectable through lightweight version metadata
- canonical builds are observable without persisting cognition payloads
- selection preview reports input versions while preserving read-only ranking
- planner and runtime execution behavior remain unchanged

## Non-Goals

Phase 2 does not introduce:

- agent behavior
- an LLM planner or external model provider
- a memory system
- embeddings or semantic retrieval
- autonomous loops
- automatic recommendation promotion
- automatic proposal approval
- automatic tool invocation or execution
- persisted cognitive-state payloads
- hidden multi-step reasoning

## Future Extensions

Future work may add:

- richer bounded planner-input diagnostics
- explicit projection rebuild support and rebuild tooling
- adapter-provided planner inputs behind the canonical builder boundary
- persisted snapshot audit events, if historical reconstruction later requires
  them

These extensions must preserve authoritative state ownership, avoid exposing
full cognition payloads by default, and receive separate architecture review
when they change persistence, planning, or execution semantics.
