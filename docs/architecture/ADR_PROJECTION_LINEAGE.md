# ADR: Projection Lineage And Provenance

## Status

Accepted for the Stratum v0.5.0 runtime work loop.

## Context

Projection contracts describe how a projection can be rebuilt, while manifests
and verification describe a particular output. Operators also need provenance:
which authoritative records and identifiers contributed to a derived view.

This provenance is diagnostic metadata. It is not memory and does not create a
new source of truth.

## Decision

Stratum provides a registry-driven `ProjectionLineageService`. For an explicit
source session, the service:

1. resolves the projection and schema through `ProjectionRegistry`
2. reads the declared reconstruction and authoritative source metadata
3. inspects the authoritative runtime session
4. inspects persisted events explicitly linked to that session
5. discovers generic identifiers from event metadata
6. returns deterministic source types, identifiers, and counts

Lineage is generated on demand and is not persisted.

## Lineage Versus Reconstruction

Reconstruction metadata declares the path and authoritative source required to
recreate a projection. Lineage describes the concrete session, events, and
discovered identifiers that contributed to one projection context.

## Lineage Versus Verification

Verification asks whether current and rebuilt derived content match. Lineage
asks where that content came from. A projection may verify successfully while
still requiring lineage for audit and debugging.

## Provenance Philosophy

Lineage output is generic and future-oriented:

- source types include declared sources and event-derived entity categories
- source identifiers include session, task, event, and discovered `*_id` values
- source counts summarize the authoritative inputs
- lineage versioning permits future contract evolution

Projection names are not hardcoded in lineage generation.

## Authority

The Event Store and Runtime Session State remain canonical. Projection lineage,
reconstruction metadata, manifests, hashes, verification results, and exports
remain derived diagnostic data.

Generating lineage does not mutate source state, persist projection payloads,
or trigger execution.

## Export Integration

Projection snapshot exports include lineage by default. Callers may explicitly
disable lineage inclusion when only the projection and manifest are required.

## Future Observability

Lineage can support trace exploration, dependency visualization, audit reports,
regression analysis, and source-impact diagnostics. Any future retention or
governance must preserve the authoritative boundary and remain explicitly
operator-controlled.
