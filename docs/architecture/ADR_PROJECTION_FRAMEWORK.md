# ADR: Projection Framework

## Status

Accepted as the Stratum v0.5.0 runtime work loop architecture checkpoint.

## Context

Stratum needs consistent runtime views over authoritative event and session
state. These views support inspection and downstream runtime composition, but
must not become an independent source of truth.

The v0.5.0 projection framework defines projection identity, metadata, schema
versioning, reconstruction declarations, builder contracts, registration,
read-only discovery, and explicit request-scoped rebuilds. It does not
introduce projection persistence or an execution engine.

## Decision

Stratum uses explicit projection contracts for derived runtime state.
Projection builders create fresh projection instances from authoritative state.
The runtime-owned registry validates and exposes those contracts for discovery
without constructing projections.

## Current Architecture

### Projection

`Projection` is the base model for derived runtime projections. It identifies a
model as non-authoritative projection state and requires `ProjectionMetadata`.

### ProjectionMetadata

`ProjectionMetadata` describes one projection build. It includes the projection
schema and reconstruction contract together with the build timestamp and
builder source. Metadata is regenerated for each build.

### ProjectionSchemaInfo

`ProjectionSchemaInfo` is the stable discovery contract for a projection type.
It declares:

- projection type
- schema version
- builder name
- reconstruction information

### ProjectionReconstructionInfo

`ProjectionReconstructionInfo` documents how a projection can be recreated. It
declares:

- projection type
- reconstruction source
- `rebuildable: true`
- authoritative source

This information is descriptive. It does not execute reconstruction.

### BaseProjectionBuilder

`BaseProjectionBuilder` is the common builder protocol. A builder publishes its
schema contract and builds fresh projection results from source identifiers
without mutating authoritative state.

### ProjectionRegistry

`ProjectionRegistry` is runtime-owned. It:

- validates contracts during registration
- enforces unique projection types
- looks up registered builders
- exposes schema and reconstruction metadata
- enumerates registered projection types

The registry does not build projections.

### Projection Rebuild Service

`ProjectionRebuildService` resolves a named builder through the registry,
revalidates its contract, builds fresh projection data from an explicit source
identifier, and validates the result metadata against the registered contract.
It returns the projection data together with reconstruction metadata and
started/completed diagnostics. Invalid results return a failed diagnostic.

Rebuilds are explicit API operations. They do not cache or persist projection
payloads and do not schedule further work.

### DecisionProjection

`DecisionProjection` is a derived decision summary. Its builder reconstructs it
from runtime session state and declares `runtime_session` as authoritative.

### SessionDecisionProjection

`SessionDecisionProjection` is a derived session-level aggregation of decision
projections. Its builder uses decision projections as its reconstruction input
and ultimately declares `runtime_session` as authoritative.

## State Authority

### Authoritative State

- Event Store
- Runtime Session State

Authoritative state owns durable runtime facts and remains the source used to
reconstruct derived views.

### Derived State

- `PlanningContext`
- `CognitiveState`
- `DecisionProjection`
- `SessionDecisionProjection`

Derived state may be discarded and recreated. It must not be treated as the
source of truth for runtime facts.

## Projection Principles

- Projections are derived.
- Projections are disposable.
- Projections are rebuildable.
- Projections are non-authoritative.

## Registry Principles

- The registry provides discovery only.
- The registry does not build projections.
- The registry does not cache projections.
- The registry does not persist projections.
- Registry endpoints expose contract metadata, not projection payloads.

## Reconstruction Principles

- Every projection declares its authoritative source.
- Every projection declares its reconstruction source.
- Projection contracts are validated when registered.
- Projection contracts and rebuilt results are validated during rebuild.
- Invalid contracts fail fast.
- Invalid rebuilds fail with structured diagnostics.
- Validation protects reconstruction assumptions.
- Reconstruction metadata identifies the canonical inputs used by a rebuild.

## Rebuild Uses

Explicit rebuild is intended for diagnostics, recovery, and verification.
Rebuild output remains derived state. Producing or inspecting a rebuild does
not create authority, replace Event Store facts, or replace Runtime Session
State.

## Consequences

Projection construction remains builder-owned and request-scoped. Schema and
reconstruction metadata support compatibility and inspection without creating
new authority, storage, caching, replay, or automatic execution behavior.

## Future Roadmap

Potential future capabilities include:

- Projection Engine
- Projection Replay

These capabilities are explicitly not implemented in Stratum v0.5.0. Any future
implementation must preserve the boundary between authoritative state and
derived projections.
