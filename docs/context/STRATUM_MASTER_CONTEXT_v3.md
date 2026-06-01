# STRATUM_MASTER_CONTEXT_v3.md

# STRATUM — Master Architecture & Context Document

Version: 3.0 — May 2026

## Architectural Positioning

Stratum is:
- a local-first execution runtime
- a governed AI engineering workstation
- a deterministic agent harness
- a repository transformation runtime
- a provider-agnostic engineering runtime kernel

---

# Core Design Principles

## Runtime First

Stratum owns:
- execution lifecycle
- approvals
- observability
- persistence
- reliability policy
- human intervention

Frameworks are optional future adapters.

---

## Deterministic Core

The runtime kernel should remain:
- small
- inspectable
- composable
- auditable

Avoid hidden orchestration magic.

---

## Tool-Driven Cognition

Everything is a tool:
- ask_human
- observe
- read_file
- write_file
- load_skill
- run_shell

No special orchestration branches.

---

## Adapter-First Extensibility

Future systems should connect through adapters:
- MCP
- Codex tooling
- Claude tooling
- CAMEL
- LangGraph
- AutoGen
- CrewAI
- VSCode integrations
- Telegram interfaces
- TUI frontends

without rewriting runtime foundations.

---

# Runtime Layering Model

## Layer 1 — UI / Transport
- Tauri desktop app
- HTML fallback UI
- future TUI
- future Telegram
- future VSCode bridge

## Layer 2 — API Surface
FastAPI endpoints:
- /task
- /stream
- /pending
- /respond
- /interrupt
- /stop
- /budget
- /proposals
- /history

## Layer 3 — Runtime Kernel
Core:
- ReAct loop
- iteration discipline
- tool dispatch
- interrupt handling
- stop handling

File:
- agent/core.py

## Layer 4 — Tool Execution Layer
Responsibilities:
- filesystem operations
- shell execution
- observability
- human interaction
- skill loading

## Layer 5 — Reliability Layer
Responsibilities:
- severity classification
- error budgets
- reflection gating
- proposal workflows

Files:
- budget.py
- reflect.py

## Layer 6 — Persistence + Event Layer
Responsibilities:
- SQLite persistence
- append-only traces
- event streaming
- artifacts
- history

## Layer 7 — Provider Layer
Supported:
- Anthropic
- OpenAI-compatible APIs
- OpenRouter
- Gemini
- Groq
- Ollama
- Vast.ai-hosted inference

---

# Runtime Event Philosophy

Every meaningful runtime action emits a structured event.

Examples:
- task_started
- plan_generated
- tool_called
- tool_result
- warning
- ask_human
- proposal_generated
- reflection_triggered
- task_completed

Event streams become:
- observability substrate
- replay substrate
- future memory substrate
- orchestration substrate

---

# Event Bus Direction

MVP:
- SQLite append
- SSE broadcast

Future:
emit(event)
subscribe(event_type)

---

# Tool Registry Evolution

Future-ready architecture:
- name
- description
- schema
- risk_level
- requires_approval

This enables:
- MCP compatibility
- UI auto-generation
- risk-aware execution

---

# Human Posture Model

## In The Loop
Blocking interaction through ask_human()

## Above The Loop
Live governance through:
- observe()
- interrupt
- stop

## Out Of The Loop
Post-task governance:
- RCA review
- proposal approval
- trace replay

---

# Reliability Philosophy

Stratum applies SRE concepts to AI runtime systems.

Includes:
- severity taxonomy
- rolling error budgets
- gated reflection
- evidence-backed proposals

---

# Skills Philosophy

Skills define:
- methodology
- process
- engineering discipline

Python defines:
- runtime mechanics

Never mix the two.

---

# Repository Transformation Runtime

Primary benchmark domain:
Transforming repositories safely.

Examples:
- Electron → Tauri migration
- SaaS → local-first conversion
- enterprise feature stripping
- telemetry removal
- infrastructure simplification

---

# Scope Discipline

TRUE MVP includes ONLY:
- HITL
- observe()
- event streaming
- ReAct loop
- SQLite persistence
- error budgets
- proposal lifecycle
- Tauri shell
- core tools

Avoid premature complexity:
- swarms
- autonomous recursion
- advanced memory
- browser automation
- distributed execution

---

# Final Principle

Stratum is fundamentally:

“An observable execution harness for probabilistic engineering systems.”
