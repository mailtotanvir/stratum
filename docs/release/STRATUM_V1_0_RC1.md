# Stratum v1.0 RC1

This directory freezes the v1.0 release candidate documentation set.

## Included Documents

- [Architecture Guide](ARCHITECTURE_GUIDE.md)
- [Operator Guide](OPERATOR_GUIDE.md)
- [Developer Guide](DEVELOPER_GUIDE.md)
- [Extension SDK Guide](EXTENSION_SDK_GUIDE.md)
- [API Reference](API_REFERENCE.md)
- [ADR Index](ADR_INDEX.md)
- [Release Notes](RELEASE_NOTES.md)
- [Migration Notes](MIGRATION_NOTES.md)
- [Roadmap Beyond v1](ROADMAP_BEYOND_V1.md)
- [Known Limitations](KNOWN_LIMITATIONS.md)

## Freeze Statement

No new platform capabilities are introduced in RC1.

The release candidate validates that:

- the Runtime Event Store is authoritative
- derived state remains deterministic
- provider selection is abstracted behind execution contracts
- agent execution is adapter-based rather than framework-bound
- operator governance is explicit and replayable
- the desktop console and backend runtime remain separated by the WSL/localhost boundary

## Release Artifacts

- architecture diagram
- runtime flow diagram
- operator console screenshots
- sample engineering workflow
- sample repository transformation
- sample evaluation report
- sample replay
- sample extension
- sample skill

The assets are represented in this repository as reproducible diagrams and frozen
documentation entries. Runtime screenshots and sample outputs should be captured
during release validation from the desktop console and backend services.
