# Stratum

Local-first AI-assisted engineering runtime workstation.

Stratum v1.0 RC1 freezes the platform as a deterministic, provider-agnostic,
agent-agnostic runtime for governed engineering work. The authoritative source
of truth remains the Runtime Event Store; projections, summaries, and UI state
are derived.

## Release Hub

- [Release Candidate Index](docs/release/STRATUM_V1_0_RC1.md)
- [Architecture Guide](docs/release/ARCHITECTURE_GUIDE.md)
- [Operator Guide](docs/release/OPERATOR_GUIDE.md)
- [Developer Guide](docs/release/DEVELOPER_GUIDE.md)
- [Extension SDK Guide](docs/release/EXTENSION_SDK_GUIDE.md)
- [API Reference](docs/release/API_REFERENCE.md)
- [ADR Index](docs/release/ADR_INDEX.md)
- [Release Notes](docs/release/RELEASE_NOTES.md)
- [Migration Notes](docs/release/MIGRATION_NOTES.md)
- [Roadmap Beyond v1](docs/release/ROADMAP_BEYOND_V1.md)
- [Known Limitations](docs/release/KNOWN_LIMITATIONS.md)

## Structure

- `backend/` - FastAPI backend runtime and query/observability services
- `desktop/` - React/Vite operator console
- `docs/` - architecture, context, release, and validation material
- `workspace/` - local working area
- `logs/` - runtime logs
- `artifacts/` - generated task artifacts
