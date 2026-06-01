
# STRATUM v1 — Engineering Specification (Extended)

## Poor-Man’s AI-Assisted Engineering Runtime Workstation

### Built with Codex + Local Runtime + Frontier/Free Models

Version: 2.1
Date: May 2026

---

# EXTENSIBILITY ADDENDUM

This addendum extends the original STRATUM_V1_ENGINEERING_SPEC.md.

The primary architectural principle is now formally defined as:

> Stratum is a runtime substrate with stable interfaces, not a vertically integrated proprietary agent framework.

This ensures:
- future interoperability
- ecosystem compatibility
- adapter-driven extensibility
- protocol-oriented growth
- avoidance of framework lock-in

---

# 1. Extensibility Philosophy

## Core Principle

Stratum must remain:
- provider-agnostic
- orchestration-agnostic
- memory-agnostic
- transport-agnostic
- UI-agnostic

The runtime core owns:
- tasks
- approvals
- execution
- persistence
- events
- artifacts
- logs

External systems integrate through adapters/interfaces.

---

# 2. Runtime-First Architecture

The runtime owns:
- execution lifecycle
- approvals
- observability
- task state
- event emission
- persistence

Agent systems are optional orchestration layers above the runtime.

---

# 3. Adapter-First Design

Stratum should prefer:
- adapters
- connectors
- protocol compatibility

over:
- proprietary abstractions
- custom orchestration DSLs
- tightly coupled frameworks

---

# 4. Future Integration Compatibility

The architecture should preserve compatibility with future ecosystems including:

- OpenAI-compatible APIs
- MCP (Model Context Protocol)
- Claude tooling ecosystems
- Codex tooling ecosystems
- CAMEL
- AutoGen
- CrewAI
- LangGraph
- VSCode AI extensions
- TUI runtimes
- Telegram runtimes
- Open-source memory systems
- local inference runtimes
- Ollama
- Vast.ai deployments

WITHOUT requiring core runtime rewrites.

---

# 5. Event-Driven Runtime

All major runtime actions must emit structured events.

Examples:
- task_started
- repo_scanned
- patch_generated
- command_executed
- approval_requested
- artifact_created

This event stream becomes:
- observability substrate
- memory substrate
- orchestration substrate
- evaluation substrate

---

# 6. Memory System Philosophy

Memory should belong to the runtime infrastructure.
NOT to individual models or agents.

MVP memory is intentionally minimal:
- task history
- event logs
- artifacts
- repo summaries
- approval traces

Future adapters may include:
- Chroma
- Qdrant
- SQLite semantic indexing
- graph memory systems
- open-source memo systems

---

# 7. Orchestration Philosophy

Stratum MVP intentionally avoids:
- recursive swarms
- autonomous worker spawning
- uncontrolled delegation

However, the architecture must preserve future compatibility with:
- CAMEL
- LangGraph
- AutoGen
- CrewAI
- custom orchestrators

via orchestration adapters.

---

# 8. Repository Transformation Benchmark

Stratum is fundamentally a:

> Repository Transformation Runtime

Supported future transformation workflows may include:
- Electron → Tauri migration
- SaaS → local-first conversion
- removing enterprise/cloud orchestration
- simplifying multi-user systems
- stripping telemetry
- reducing infrastructure complexity
- replacing external APIs with local inference

---

# 9. Harness Engineering Philosophy

Stratum itself is a harness engineering platform.

The harness includes:
- provider routing
- execution safety
- approvals
- rollback systems
- runtime state
- event emission
- artifact tracking

Future agents/orchestrators operate INSIDE the harness rather than replacing it.

---

# 10. Final Extensibility Rule

The runtime core should remain:
- small
- deterministic
- observable
- composable

Complexity should accumulate at adapter layers rather than runtime foundations.
