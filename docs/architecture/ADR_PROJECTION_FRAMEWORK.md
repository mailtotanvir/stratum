# ADR: Projection Framework

## Status

Accepted for Stratum v0.5.0 runtime work loop.

## Context

Stratum exposes runtime views derived from authoritative session and event-backed
state. These views need a common identity, build contract, and metadata without
introducing persistence or changing runtime, planner, execution, or agent
behavior.

## Decision

Runtime projection models inherit from `Projection` and include
`ProjectionMetadata`. Projection builders satisfy the `BaseProjectionBuilder`
protocol and return fresh projection instances from authoritative source state.

Metadata identifies the projection type, build time, builder source, and schema
version. It describes a specific build and is regenerated whenever a projection
is rebuilt.

## Projection Principles

- Projections are derived.
- Projections are disposable.
- Projections are rebuildable.
- Projections never become a source of truth.

## Projection Registry Principles

- The registry discovers projections.
- The registry does not own state.
- The registry does not persist projections.
- The registry does not cache projections.
- The registry does not become authoritative.

## Consequences

Projection metadata is diagnostic and versioning information, not authoritative
runtime state. Builders may read authoritative services and emit existing
diagnostic events, but they must not mutate source state. This framework adds no
projection engine, projection persistence, projection caching, memory system,
planner behavior, execution behavior, agent behavior, or autonomous execution.
