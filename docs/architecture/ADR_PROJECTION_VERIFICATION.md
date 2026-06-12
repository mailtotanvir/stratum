# ADR: Projection Consistency Verification

## Status

Accepted for the Stratum v0.5.0 runtime work loop.

## Context

Projections are derived views over authoritative Event Store and Runtime
Session State. A projection can drift when its current derived content no
longer matches content produced from the same authoritative source.

Stratum does not persist projections as authoritative state. Verification must
therefore remain explicit, request-scoped, deterministic, and non-mutating.

## Decision

Stratum provides a projection verification service that:

1. resolves the named builder through `ProjectionRegistry`
2. loads the current request-scoped projection for an explicit source
3. independently rebuilds the projection through `ProjectionRebuildService`
4. compares normalized projection content and reconstruction metadata
5. returns deterministic field-level differences and diagnostics

The independently rebuilt value is the expected value. The current derived
value is the actual value.

## Projection Drift

Projection drift is any content or contract difference between the current
derived view and a fresh rebuild from the same authoritative source. Difference
types are:

- `missing_field`
- `unexpected_field`
- `value_mismatch`
- `metadata_mismatch`

Volatile `built_at` timestamps are excluded from comparison because separate
request-scoped builds necessarily have different construction times. Schema,
builder, source, and reconstruction metadata remain comparable.

## Authority

The Event Store and Runtime Session State remain canonical. PlanningContext,
CognitiveState, and registered projections remain derived and rebuildable.
Verification does not promote a projection, comparison result, or diagnostic
event into authoritative runtime state.

## Rebuild Versus Verify

Rebuild produces a fresh projection from authoritative inputs. Verify loads the
current derived view, performs an independent rebuild, and compares the two.
Neither operation persists projection payloads or mutates runtime/session
state.

## Diagnostics

Verification emits:

- `projection_verification_started`
- `projection_verification_completed`
- `projection_verification_failed`

Diagnostics include projection name, builder name, schema version, and
difference count.

## Future Projection Governance

Future governance may define policies for tolerated differences, schema
migration checks, verification schedules, or operator review. Such governance
must remain explicit and must not introduce automatic execution, autonomous
loops, or a new source of truth.
