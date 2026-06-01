# STRATUM v1 — Engineering Specification
## Poor-Man’s AI-Assisted Engineering Runtime Workstation
### Built with Codex + Local Runtime + Frontier/Free Models

**Version:** 2.0 MVP Spec  
**Date:** May 2026  
**Primary Builder:** OpenAI Codex CLI  
**Operator:** Tanvir  
**Architecture Style:** Deterministic AI Engineering Runtime  
**Philosophy:** Local-first • Token-efficient • Human-approved execution • Provider-agnostic • Incremental engineering

---

# 1. Executive Summary

Stratum is a local AI-assisted engineering workstation designed to:
- inspect repositories
- ingest engineering specs/context markdown
- reason about codebases
- propose modifications
- execute approved commands
- apply file changes
- stream execution logs
- track artifacts/history

This is NOT:
- an AGI platform
- an autonomous recursive agent swarm
- a Devin clone
- a browser-autonomous system

This IS:
- a deterministic engineering runtime
- a human-in-the-loop AI coding workstation
- a poor-man’s Antigravity-inspired operator console
- a Codex-driven local engineering platform

The design prioritizes:
- low cost
- local execution
- provider switching
- operational visibility
- safety through approval gates
- reproducibility
- incremental extensibility

---

# 2. Core MVP Philosophy

## MVP Goal

Given:
- a local repository
- a markdown engineering specification
- a context markdown file

Stratum should:
1. inspect the repository
2. load context/spec markdown
3. generate a migration/refactor plan
4. propose file edits + commands
5. request operator approval
6. execute approved actions
7. stream logs live
8. maintain history/artifacts
9. allow iterative engineering sessions

---

# 3. Hard Constraints

| Constraint | Decision |
|---|---|
| OS | Windows 11 + WSL2 |
| Repo location | WSL native filesystem |
| Runtime | WSL2 Ubuntu 22.04 |
| Python | 3.11 ONLY for project |
| Python manager | uv |
| Node manager | pnpm |
| Desktop shell | Tauri v2 |
| UI | React + Vite + Tailwind |
| Database | SQLite |
| Backend | FastAPI |
| AI Runtime | Custom deterministic orchestration |
| Agent framework | NOT core MVP |
| Browser automation | Excluded from MVP |
| Document parsing | Markdown/plaintext only |
| Sandbox model | Human approval gates |
| Architecture | Monorepo |
| Workflow | Terminal-first Codex CLI |

---

# 4. Non-Goals (Critical)

These are explicitly OUT OF SCOPE for MVP:

- multi-agent swarms
- recursive delegation
- autonomous browsing
- self-improving systems
- vector databases
- RAG pipelines
- PDF parsing
- distributed execution
- cloud orchestration
- Docker/Kubernetes
- collaborative multi-user systems
- plugin marketplace
- authentication
- remote internet execution
- browser automation
- mobile support

Any attempt to include these in MVP is architectural drift.

---

# 5. Final MVP Architecture

```text
Operator
   │
   ▼
Tauri Desktop UI
   │
   ▼
FastAPI Runtime
   │
   ├── Context Loader
   ├── Repo Inspector
   ├── Provider Router
   ├── Prompt Builder
   ├── Approval Gate
   ├── Command Runner
   ├── Patch Engine
   ├── Artifact Tracker
   ├── Git Safety Layer
   └── SSE Event Streamer
```

---

# 6. Monorepo Structure

```text
stratum/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── runtime/
│   │   ├── providers/
│   │   ├── tools/
│   │   ├── models/
│   │   ├── db/
│   │   ├── services/
│   │   ├── schemas/
│   │   ├── utils/
│   │   └── main.py
│   │
│   ├── tests/
│   ├── scripts/
│   ├── pyproject.toml
│   └── .env
│
├── desktop/
│   ├── src/
│   ├── src-tauri/
│   ├── public/
│   ├── package.json
│   └── vite.config.ts
│
├── docs/
│   ├── specs/
│   ├── context/
│   ├── architecture/
│   └── prompts/
│
├── artifacts/
├── logs/
├── workspace/
├── .gitignore
├── README.md
└── STRATUM_SPEC.md
```

---

# 7. Recommended Technology Stack

## Backend

| Component | Choice |
|---|---|
| Python | 3.11 |
| API | FastAPI |
| ASGI | uvicorn |
| Validation | pydantic v2 |
| Config | pydantic-settings |
| DB ORM | SQLAlchemy 2 |
| DB | SQLite |
| Logging | loguru |
| Rich terminal logs | rich |
| HTTP client | httpx |
| AI provider SDKs | OpenAI-compatible abstraction |

---

## Frontend

| Component | Choice |
|---|---|
| Framework | React |
| Build | Vite |
| Language | TypeScript |
| Styling | Tailwind |
| SSE | native EventSource |
| State | Zustand |
| Desktop | Tauri v2 |

---

# 8. Python Environment Strategy

## CRITICAL RULE

Never use:
- base conda
- system python
- Windows Python

for Stratum.

---

## Install Python 3.11

Inside WSL:

```bash
sudo apt update
sudo apt install software-properties-common -y
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev -y
```

---

## Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart shell.

Verify:

```bash
uv --version
```

---

# 9. Node + pnpm Setup

```bash
npm install -g pnpm
```

Verify:

```bash
pnpm -v
```

---

# 10. Tauri Setup

## Install prerequisites

Inside Windows PowerShell:

```powershell
winget install Rustlang.Rustup
winget install Microsoft.VisualStudio.2022.BuildTools
```

Select:
- Desktop C++ workload

---

## Install Tauri CLI

Inside WSL:

```bash
cargo install tauri-cli
```

Verify:

```bash
cargo tauri --version
```

---

# 11. AI Provider Architecture

## Design Requirement

Provider-agnostic from day one.

Never tightly couple to:
- OpenAI SDK
- CAMEL
- Anthropic SDK

---

## Provider Interface

```python
class BaseProvider:
    async def chat(self, messages, model, stream=False):
        pass
```

---

## MVP Providers

| Provider | Status |
|---|---|
| OpenRouter | YES |
| OpenAI | YES |
| Ollama | YES |
| Groq | YES |
| Gemini | Later |
| Anthropic | Later |

---

# 12. Provider Routing Strategy

## Goal

Cheap models for:
- repo scanning
- summarization
- planning

Better models for:
- critical patch generation
- architecture decisions

---

# 13. Runtime Pipeline

## Core Execution Flow

```text
User submits task
    ↓
Load markdown context
    ↓
Inspect repository
    ↓
Generate execution plan
    ↓
Show approval UI
    ↓
Execute approved steps
    ↓
Stream logs
    ↓
Track artifacts/history
    ↓
Generate completion summary
```

---

# 14. Git Safety Layer (MANDATORY)

Before ANY modification:

## System must:

1. detect git repo
2. create feature branch
3. checkpoint commit
4. store rollback reference

---

# 15. Approval Model

## Default Policy

All destructive operations require approval.

---

# 16. Command Execution Model

## MVP Policy

Commands are:
1. generated
2. previewed
3. approved
4. executed
5. logged

---

# 17. Database Schema (MVP)

## Tables

### tasks

```text
id
title
status
created_at
completed_at
provider
model
summary
```

### events

```text
id
task_id
type
message
timestamp
```

### artifacts

```text
id
task_id
path
type
created_at
```

---

# 18. Markdown Context Ingestion

## MVP ONLY

Supported:
- .md
- .txt

NOT:
- PDF
- DOCX
- vector indexing

---

# 19. SSE Event Streaming

## Event Types

```text
task_started
context_loaded
repo_scanned
plan_generated
approval_requested
command_started
command_output
patch_applied
artifact_created
task_completed
task_failed
```

---

# 20. Frontend Screens

## MVP Screens

### 1. Task Console
- task input
- provider selector
- model selector

### 2. Live Event Log
- streaming runtime logs
- command outputs
- errors

### 3. Approval Panel
- pending approvals
- approve/reject buttons

### 4. Artifact Viewer
- changed files
- generated markdown
- summaries

### 5. Task History
- previous runs
- timestamps
- statuses

---

# 21. Codex Workflow Strategy

## CRITICAL RULE

Codex should NEVER receive:
- giant open-ended prompts
- vague architecture tasks
- entire-system rewrites

---

## Preferred Workflow

### Small bounded tasks

Example:

```text
Implement SSE event endpoint with FastAPI.
Acceptance criteria:
- /stream endpoint works
- emits heartbeat every 5s
- React EventSource client receives messages
- unit test included
```

---

# 22. Codex Guardrails

## ALWAYS

- checkpoint git before changes
- validate after each milestone
- test incrementally
- keep tasks scoped
- commit frequently

---

# 23. Anti-Patterns

## DO NOT BUILD

### Fake autonomy theater

Bad:
```text
10 agents debating endlessly
```

Good:
```text
1 deterministic runtime pipeline
```

---

# 24. Logging Strategy

## Log EVERYTHING

Required:
- commands
- approvals
- provider usage
- token estimates
- errors
- execution time

---

# 25. First Milestone Plan

## Phase 0 — Bootstrap

### Acceptance Criteria

- repo initialized
- uv working
- pnpm working
- Python 3.11 working
- Tauri CLI installed
- FastAPI hello-world works
- React hello-world works

---

# 26. Phase 1 — Backend Runtime

## Deliverables

- FastAPI app
- SQLite integration
- task model
- SSE streaming
- event logging
- provider abstraction

---

# 27. Phase 2 — Frontend Console

## Deliverables

- Tauri shell
- task input
- SSE log viewer
- provider selector
- approval panel

---

# 28. Phase 3 — Repo Runtime

## Deliverables

- git safety layer
- repo scanner
- markdown ingestion
- command execution
- approval workflow

---

# 29. Phase 4 — AI-Assisted Migration

## Benchmark Deliverable

Input:
- Electron/PWA repo
- migration spec
- context markdown

Output:
- migration plan
- proposed patches
- approved execution
- artifact summary

---

# 30. Testing Strategy

## Required

### Backend
- pytest
- integration tests
- SSE tests

### Frontend
- minimal Vitest
- smoke tests only

### Runtime
- command execution tests
- rollback validation
- approval flow tests

---

# 31. Recovery Workflow

If runtime becomes unstable:

## Recovery Steps

1. stop runtime
2. revert git branch
3. inspect logs
4. restore checkpoint
5. rerun smaller task

---

# 32. Cost Strategy

## Philosophy

Use:
- cheap/free models for broad reasoning
- premium models selectively

This is central to Stratum.

---

# 33. Long-Term Evolution Path

## MVP+
- provider capability routing
- local embeddings
- repo memory
- semantic search

## V2
- CAMEL integration
- lightweight worker delegation
- browser automation

## V3
- remote runtime
- Vast.ai orchestration
- Ollama clusters
- advanced operator UI

---

# 34. Final Engineering Principles

## Principle 1
Determinism over fake autonomy.

## Principle 2
Visibility over magic.

## Principle 3
Approval over uncontrolled execution.

## Principle 4
Incremental delivery over ambitious architecture.

## Principle 5
Cheap models for broad work.
Premium models for precision work.

---

# 35. First Night Build Order

## EXACT ORDER

### 1.
Create repo

### 2.
Install Python 3.11

### 3.
Install uv

### 4.
Create backend

### 5.
Initialize FastAPI

### 6.
Initialize React/Vite

### 7.
Initialize Tauri

### 8.
Implement SSE hello-world

### 9.
Implement task persistence

### 10.
Implement provider abstraction

DO NOT skip ahead.

---

# 36. Final Codex Operational Advice

## Codex works best when:
- scope is explicit
- tasks are bounded
- acceptance criteria are concrete
- architecture is stable
- checkpoints are frequent

## Codex performs poorly when:
- requirements mutate constantly
- prompts become massive
- architecture is ambiguous
- too many moving systems exist simultaneously

---

# 37. MVP Definition of Success

Stratum v1 succeeds if:

You can:
1. point it at a repo
2. load markdown specs/context
3. generate a migration/refactor plan
4. approve commands and edits
5. execute transformations safely
6. stream logs live
7. maintain history/artifacts
8. iterate cheaply across providers

That alone is already a serious engineering workstation.
