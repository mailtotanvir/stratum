# Extension SDK Guide

## Intent

Extensions let Stratum grow without changing core runtime semantics.

## Boundaries

- Providers are integrated through provider infrastructure and routing contracts.
- Agents are integrated through execution participant and adapter contracts.
- Skills extend engineering intelligence without becoming core runtime logic.
- MCP and A2A readiness are adapter concerns, not kernel concerns.

## Rules

- Extensions must not bypass the event store.
- Extensions must preserve deterministic reconstruction.
- Extensions must emit explicit diagnostics and lineage where applicable.
