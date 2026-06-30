# Stratum v1.0 Epic Roadmap

## Purpose

This roadmap resets v1 execution from small file-level tasks to larger epics. The runtime architecture remains:
- deterministic runtime core
- FastAPI backend in WSL
- Tauri/React desktop as operator console
- provider-agnostic execution
- agent marketplace and adapter independence
- MCP and A2A as adapter-level concerns
- event store as source of truth
- memory and projections derived from events and artifacts

## Execution Rules

- Work one epic at a time unless an epic explicitly depends on a prior one.
- Complete the milestone boundary inside the epic before switching.
- Prefer end-to-end slices over isolated file edits.
- Use checkpoint commits only at stable epic boundaries or before high-risk pivot points.
- Keep backend and desktop changes aligned with the epic boundary, not with individual files.

## Epic 1. Runtime Foundation Completion

- Goal: finish the deterministic runtime core so the system has a stable event-first execution substrate.
- Scope: event store writes, replayable runtime state, deterministic task lifecycle, projection rebuild hooks, approval/event emission contracts.
- Out of scope: marketplace, skills, external adapters, advanced UI, semantic memory, evaluation automation.
- Validation strategy: event append/replay smoke, lifecycle integrity checks, source-of-truth invariants, minimal integration tests.
- Commit/checkpoint rule: checkpoint after the event model and runtime lifecycle are stable and replayable.
- Dependencies: existing runtime/persistence skeleton, current backend query/observability foundations.

## Epic 2. Operator Console MVP

- Goal: make Tauri/React the primary operator console for runtime control and visibility.
- Scope: session overview, task launch, event stream view, approvals panel, status cards, basic navigation.
- Out of scope: deep analytics, marketplace browsing, advanced memory inspection, external protocol management.
- Validation strategy: local desktop launch, UI smoke path, backend connection verification, operator flow walk-through.
- Commit/checkpoint rule: checkpoint when the console can start, connect, and display a live runtime session.
- Dependencies: runtime foundation, API endpoints for session/status/events.

## Epic 3. End-to-End Runtime Session Flow

- Goal: deliver a full operator-to-runtime session from task creation through completion summary.
- Scope: task intake, plan generation, approval gating, execution loop, live event streaming, completion record.
- Out of scope: provider optimization, marketplace management, adapter ecosystems, long-term memory systems.
- Validation strategy: single-session happy path, recovery from pause/resume, event trace completeness, manual end-to-end smoke.
- Commit/checkpoint rule: checkpoint after a full session can be run repeatedly without manual repair.
- Dependencies: Epic 1, Epic 2.

## Epic 4. Workspace & Repository Operations

- Goal: make repository inspection and workspace operations reliable and governed.
- Scope: repo discovery, workspace selection, file/system inspection, patch staging, command execution boundaries, artifact placement.
- Out of scope: external browsing, distributed workspaces, multi-repo orchestration, full IDE integration.
- Validation strategy: workspace attach/detach smoke, repo scan accuracy, command sandbox checks, patch application verification.
- Commit/checkpoint rule: checkpoint when workspace operations are deterministic and reversible enough for routine use.
- Dependencies: Epic 1, Epic 3.

## Epic 5. Approval and Human Intervention UX

- Goal: make human approval and interruption flows clear, fast, and trustworthy.
- Scope: approval queue, ask/respond loop, interrupt/stop flows, pending decision visibility, action-risk presentation.
- Out of scope: autonomous approval bypass, policy authoring studio, multi-user governance, long-form chat UX.
- Validation strategy: approval lifecycle tests, interrupt/stop smoke, UI state transitions, event/audit trace verification.
- Commit/checkpoint rule: checkpoint when every gated action has a visible decision path and audit trail.
- Dependencies: Epic 1, Epic 2, Epic 3.

## Epic 6. Provider Operations and Cost Governance

- Goal: keep provider usage swappable, observable, and cost-aware.
- Scope: provider routing, execution logging, token/cost telemetry, fallback policy, budget policy, model selection metadata.
- Out of scope: provider-specific UI sprawl, provider lock-in, training pipelines, autonomous provider ranking loops.
- Validation strategy: provider routing smoke, budget enforcement checks, cost-report correctness, fallback path tests.
- Commit/checkpoint rule: checkpoint when provider choice is isolated behind stable interfaces and budgets are enforced.
- Dependencies: Epic 1, current provider abstraction work.

## Epic 7. Agent Marketplace Foundation

- Goal: define the marketplace and adapter model without coupling runtime core to any single agent ecosystem.
- Scope: adapter registry, capability descriptors, install/enable metadata, contract boundaries, marketplace listing shape.
- Out of scope: agent framework implementation, orchestration lock-in, protocol-specific runtime behavior, autonomous swarms.
- Validation strategy: adapter registration tests, contract compliance checks, marketplace listing resolution, independence invariants.
- Commit/checkpoint rule: checkpoint when adapters can be listed and selected without changing core runtime semantics.
- Dependencies: Epic 1, Epic 6.

## Epic 8. Skills & Memory v1

- Goal: provide minimal skills and memory primitives derived from runtime events and artifacts.
- Scope: skill registry/loading, memory projections, task summaries, artifact-linked memory, rebuildable derived views.
- Out of scope: vector DB dependence, hard-coded long-term semantic memory, agent-owned memory, self-modifying knowledge loops.
- Validation strategy: projection rebuild tests, artifact-to-memory traceability, skill load smoke, derived-state consistency checks.
- Commit/checkpoint rule: checkpoint when memory can be regenerated from events and artifacts alone.
- Dependencies: Epic 1, Epic 4, Epic 7.

## Epic 9. Evaluation and Regression Harness v1

- Goal: add basic evaluation and regression coverage so runtime quality can be measured over time.
- Scope: evaluation records, simple evaluators, regression fixtures, run-to-run comparison, acceptance criteria capture.
- Out of scope: complex benchmark farms, model training, autonomous score optimization, broad analytics platforming.
- Validation strategy: repeatable regression runs, evaluator determinism checks, result diffing, coverage of core runtime flows.
- Commit/checkpoint rule: checkpoint when evaluations are stable enough to compare runs across provider/model changes.
- Dependencies: Epic 1, Epic 3, Epic 6.

## Epic 10. Runtime Observability and Replay

- Goal: make the runtime inspectable through replay, trace views, and event-driven observability.
- Scope: replay views, event timelines, trace filtering, projection invalidation/rebuild visibility, operational diagnostics.
- Out of scope: enterprise monitoring stack, remote telemetry pipeline, opaque analytics, non-deterministic dashboards.
- Validation strategy: replay fidelity checks, event timeline completeness, observability UI smoke, recovery-path verification.
- Commit/checkpoint rule: checkpoint when a historical session can be reconstructed from the event store and artifacts.
- Dependencies: Epic 1, Epic 3, Epic 8.

## Epic 11. Artifact and Patch Lifecycle

- Goal: formalize artifact creation, patch management, and lifecycle tracking for operator trust and recovery.
- Scope: artifact registry, patch provenance, file/change linkage, generated summaries, rollback references, retention rules.
- Out of scope: full document management system, collaborative review workflows, cloud artifact storage, binary asset pipelines.
- Validation strategy: patch provenance checks, artifact index consistency, rollback smoke, link integrity tests.
- Commit/checkpoint rule: checkpoint when every generated patch and artifact has traceable origin and lifecycle state.
- Dependencies: Epic 1, Epic 4, Epic 10.

## Epic 12. External Adapter Readiness: MCP/A2A

- Goal: prepare the runtime for adapter-level integration with MCP and A2A without moving those concerns into the core.
- Scope: adapter contracts, transport boundaries, request/response mapping, protocol capability metadata, integration seams.
- Out of scope: direct protocol entanglement in core runtime, default dependency on external networks, hard-coded ecosystem support.
- Validation strategy: adapter conformance tests, mock transport smoke, capability mapping verification, failure containment checks.
- Commit/checkpoint rule: checkpoint when MCP/A2A behavior is isolated behind adapter boundaries and the core remains unchanged.
- Dependencies: Epic 1, Epic 7.

## Epic 13. Packaging and Local Desktop Launch

- Goal: make local startup and operator onboarding straightforward on the target WSL/desktop setup.
- Scope: backend launch flow, desktop launch flow, packaging docs, environment checks, local-first startup guidance.
- Out of scope: cloud deployment, remote user management, mobile packaging, cross-platform hardening beyond the target setup.
- Validation strategy: clean local launch smoke, install/launch verification, dependency checks, first-run path confirmation.
- Commit/checkpoint rule: checkpoint when a fresh local environment can start backend and desktop with documented steps.
- Dependencies: Epic 2, Epic 3, Epic 4.

## Epic 14. v1.0 Stabilization and Beta Readiness

- Goal: turn the working runtime into a stable v1.0 candidate with bounded scope and reliable operator experience.
- Scope: bug burn-down, doc cleanup, acceptance hardening, release notes, final validation, beta readiness criteria.
- Out of scope: new feature expansion, major architectural changes, experimental protocol work, broad refactors.
- Validation strategy: release checklist, full smoke run, regression suite, operator acceptance pass, doc consistency review.
- Commit/checkpoint rule: checkpoint at each stabilization pass and again before release tagging.
- Dependencies: all prior epics, especially Epic 1 through Epic 13.

## Recommended Execution Order

1. Runtime Foundation Completion
1. Operator Console MVP
1. End-to-End Runtime Session Flow
1. Workspace & Repository Operations
1. Approval and Human Intervention UX
1. Provider Operations and Cost Governance
1. Agent Marketplace Foundation
1. Skills & Memory v1
1. Evaluation and Regression Harness v1
1. Runtime Observability and Replay
1. Artifact and Patch Lifecycle
1. External Adapter Readiness: MCP/A2A
1. Packaging and Local Desktop Launch
1. v1.0 Stabilization and Beta Readiness

