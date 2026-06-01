# STRATUM — Master Architecture & Context Document

> **Project codename:** Stratum  
> Personal agent-first desktop platform. Lightweight, local, BYOK. Built on open-source agent infrastructure. No cloud dependency. No vendor lock-in on the agent runtime.

-----

## 1. Project Summary

Stratum is a personal desktop application that lets you dispatch multi-agent AI workflows from a local UI, observe execution in real time, and approve or guide agent decisions through a browser-based HTML interface. It is not a coding assistant or IDE plugin. It sits alongside your existing tools as a standalone agent runtime for your personal machine.

**Design philosophy:**

- Agent-first, not chat-first. Tasks are delegated, not typed line by line.
- Open agent engine (CAMEL-AI). No dependency on any closed vendor’s CLI or runtime.
- BYOK for all LLM providers. Keys never leave the machine.
- WSL2 is the compute environment. Windows is the UI surface.
- Thin, composable layers. Each component is replaceable.

-----

## 2. Project Constraints & Environment

|Constraint   |Detail                                                                         |
|-------------|-------------------------------------------------------------------------------|
|OS           |Windows 11, WSL2 (Ubuntu) as compute layer                                     |
|Dev tooling  |Claude Code CLI (no IDE integration; Cursor used separately for review only)   |
|Working mode |Tanvir as architect/QA, Claude Code as primary builder                         |
|Agent engine |CAMEL-AI (open source, Python, pip-installable in WSL2)                        |
|LLM access   |BYOK — Anthropic, OpenAI, Gemini, or any CAMEL-supported provider              |
|Desktop shell|Tauri v2 (Rust + WebView2, Windows-native, no Node runtime)                    |
|Backend      |FastAPI (Python, WSL2), served on localhost                                    |
|Networking   |Tailscale mesh available across devices (used for future remote access, not v1)|
|Mobile       |Out of scope for v1. Roadmap item only.                                        |
|IDE          |Existing IDE kept separate. Stratum is not an IDE.                             |

-----

## 3. Reference Products

|Product                  |Relationship to Stratum                                                                                                         |
|-------------------------|--------------------------------------------------------------------------------------------------------------------------------|
|Google Antigravity       |Inspiration: agent-first workspace concept, parallel agent execution, mission control UI                                        |
|Eigent (eigent-ai/eigent)|Closest open-source structural reference. Stratum does NOT fork Eigent — too enterprise-heavy. Architecture studied, not copied.|
|Claude Cowork            |Product Eigent is designed to replicate. Stratum is more minimal.                                                               |
|CAMEL-AI OWL             |Agent runtime reference. OWL is the benchmark-optimised layer; Stratum uses the underlying Workforce primitives directly.       |

-----

## 4. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Windows Desktop                           │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │              Tauri v2 Shell (Rust)                  │   │
│   │         WebView2 → React + Tailwind UI              │   │
│   │                                                     │   │
│   │   Task input · Agent status · Artifact viewer       │   │
│   │   Live SSE log · HITL question display              │   │
│   └────────────────────┬────────────────────────────────┘   │
│                        │ HTTP (localhost)                    │
└────────────────────────┼────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                    WSL2 (Ubuntu)                            │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │            FastAPI Backend (Python)                 │   │
│   │                                                     │   │
│   │  POST /task        →  submit new task               │   │
│   │  GET  /stream      →  SSE event stream              │   │
│   │  GET  /pending     →  get current HITL question     │   │
│   │  POST /respond     →  submit human answer           │   │
│   │  GET  /artifacts   →  list task outputs             │   │
│   │  GET  /history     →  task history log              │   │
│   └────────────────────┬────────────────────────────────┘   │
│                        │                                    │
│   ┌────────────────────▼────────────────────────────────┐   │
│   │          CAMEL-AI Workforce Engine                  │   │
│   │                                                     │   │
│   │  Coordinator Agent                                  │   │
│   │    └─ Task Planner Agent                            │   │
│   │         └─ Worker Agents (specialized, parallel)    │   │
│   │                                                     │   │
│   │  WorkforceCallback  →  SSE event emitter            │   │
│   │  HttpHumanToolkit   →  asyncio.Event HITL gate      │   │
│   └────────────────────┬────────────────────────────────┘   │
│                        │                                    │
│   ┌────────────────────▼────────────────────────────────┐   │
│   │              MCP Servers (WSL2)                     │   │
│   │                                                     │   │
│   │  filesystem   →  local file read/write              │   │
│   │  browser      →  headless web automation            │   │
│   │  [docs]       →  PDF/DOCX/MD handling (v2)          │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   BYOK: API keys in WSL2 .env (gitignored)                  │
│   (Windows Credential Manager bridge considered for v2)     │
└─────────────────────────────────────────────────────────────┘
```

-----

## 5. Component Detail

### 5.1 Tauri v2 Shell

- Rust backend handles startup, window management, system tray
- WebView2 renders the React frontend
- Communicates with FastAPI over `localhost` HTTP — no Tauri IPC to WSL2 directly
- On launch: checks FastAPI health endpoint; shows “Start Backend” prompt if not running
- Packages as a single `.exe` installer for Windows

**Key constraint:** Tauri runs as a Windows process. Python/CAMEL runs in WSL2. All cross-boundary communication is HTTP on localhost. File paths must be normalised at the boundary (WSL2 `/mnt/c/...` ↔ Windows `C:\...`).

### 5.2 FastAPI Backend

Runs in WSL2 via `uvicorn`. Exposes:

|Endpoint    |Method|Purpose                                                            |
|------------|------|-------------------------------------------------------------------|
|`/health`   |GET   |Startup check from Tauri                                           |
|`/task`     |POST  |Submit task `{description, worker_config}`                         |
|`/stream`   |GET   |SSE: live agent events (task start, step, tool call, result, error)|
|`/pending`  |GET   |Returns current HITL question or `null`                            |
|`/respond`  |POST  |Submits human answer `{text}` to unblock agent                     |
|`/artifacts`|GET   |Lists generated files/outputs from last task                       |
|`/history`  |GET   |Paginated task history                                             |

**HITL gate (asyncio.Event pattern):**

```python
# One pending question at a time (single-user, personal tool)
_pending = {"question": None, "event": None, "answer": None}

async def ask_human_via_http(question: str) -> str:
    event = asyncio.Event()
    _pending.update({"question": question, "event": event, "answer": None})
    await event.wait()
    _pending["question"] = None
    return _pending["answer"]

# In POST /respond:
# Use loop.call_soon_threadsafe(event.set) if workforce runs in thread executor
```

**Critical integration note:** CAMEL’s `Workforce.process_task()` manages its own event loop. Run it in `loop.run_in_executor(None, workforce.process_task, task)` to avoid blocking FastAPI’s asyncio loop. Use `call_soon_threadsafe` for the Event bridge.

### 5.3 CAMEL-AI Workforce Engine

- Installed via `pip install camel-ai` in WSL2 virtualenv
- Version-pinned from day one (breaking changes between minor releases are common)
- Provider configured at runtime from BYOK keys in `.env`

**Worker types for v1:**

- `FileWorker` — read/write local files via MCP filesystem server
- `SearchWorker` — web search via CAMEL’s SearchToolkit
- `CodeWorker` — Python code execution via CodeExecutionToolkit
- `GeneralWorker` — catch-all for reasoning/writing tasks

**WorkforceCallback for SSE:**

```python
from camel.societies.workforce.base import WorkforceCallback

class SSECallback(WorkforceCallback):
    def on_task_start(self, task): emit_sse("task_start", task)
    def on_task_complete(self, task): emit_sse("task_complete", task)
    def on_step(self, agent, step): emit_sse("step", step)
```

**HttpHumanToolkit:**

```python
from camel.toolkits import HumanToolkit

class HttpHumanToolkit(HumanToolkit):
    def ask_human_via_console(self, question: str) -> str:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(ask_human_via_http(question))
```

### 5.4 MCP Servers

- `@modelcontextprotocol/server-filesystem` — file read/write, scoped to approved directories
- `@modelcontextprotocol/server-puppeteer` or Playwright MCP — browser automation
- Run as Node processes in WSL2, communicated with via CAMEL’s `MCPToolkit`
- v2 addition: document MCP server for PDF/DOCX/MD parsing

### 5.5 BYOK Key Management

- All keys in WSL2 `.env` file (gitignored, chmod 600)
- Loaded via `python-dotenv` at FastAPI startup
- Keys passed to CAMEL model config at workforce instantiation
- Never logged, never serialised to disk beyond `.env`
- v2: consider Windows Credential Manager via `wincred` for better security

-----

## 6. HTML HITL Interface

A standalone HTML page served by FastAPI at `/ui`. Acts as the console-equivalent for human-in-the-loop interactions. Polls `/pending` every 2 seconds. When a question arrives, renders it with a textarea and submit button. On submit, POSTs to `/respond`.

This is also the fallback UI if Tauri shell is not running — open `http://localhost:8000/ui` in any browser.

**v1 scope:** Single question at a time. Text input only. No auth (localhost only).  
**v2 scope:** Question queue, approve/reject binary actions, file diff viewer.

-----

## 7. Data Flow: Task Execution

```
User types task in Tauri UI
    │
    ▼
POST /task  →  FastAPI creates CAMEL Task object
    │
    ▼
Workforce.process_task(task) [in thread executor]
    │
    ├─ Coordinator assigns subtasks to Workers
    │       │
    │       ├─ Worker calls tool (MCP filesystem, search, code exec)
    │       │       └─ SSECallback emits step event → GET /stream → Tauri UI updates
    │       │
    │       └─ Worker calls HumanToolkit (needs approval)
    │               └─ asyncio.Event blocks
    │                       │
    │                   GET /pending → HTML UI shows question
    │                   POST /respond → Event.set() → Worker continues
    │
    └─ Task complete
            └─ SSECallback emits task_complete
            └─ Artifacts written to output dir
            └─ GET /artifacts → Tauri UI shows results
```

-----

## 8. Roadmap

### v1 — Desktop Core (target: 4 weeks)

- [ ] WSL2 Python virtualenv + CAMEL-AI pinned install
- [ ] FastAPI backend with `/task`, `/stream` (SSE), `/health`
- [ ] HITL gate: `/pending` + `/respond` + `asyncio.Event` bridge
- [ ] `HttpHumanToolkit` replacing CAMEL’s console toolkit
- [ ] `SSECallback` for live event streaming
- [ ] HTML HITL page served at `/ui`
- [ ] 2–3 worker types: File, Search, Code
- [ ] MCP filesystem server wired via `MCPToolkit`
- [ ] BYOK `.env` config with provider selection
- [ ] Tauri v2 shell: task input, SSE log viewer, artifact list
- [ ] WSL2 ↔ Windows path normalisation utility
- [ ] Task history (SQLite, via SQLAlchemy)
- [ ] Basic packaging: `cargo tauri build` → `.exe`

### v2 — Document Management

- [ ] Document worker: PDF, DOCX, Markdown read/write via MCP doc server
- [ ] Local RAG: LlamaIndex or ChromaDB over personal file corpus (WSL2)
- [ ] File diff viewer in HTML HITL UI
- [ ] Approve/reject binary actions (not just text responses)
- [ ] Windows Credential Manager for key storage

### v3 — Remote Thin Client (Tailscale)

- [ ] PWA served from FastAPI, accessible over Tailscale
- [ ] Mobile-optimised HITL UI (approve/reject, task feed)
- [ ] Push notification for pending approvals (via web push or Tailscale-routed webhook)

-----

## 9. Known Risks & Mitigations

|Risk                                                   |Likelihood|Impact|Mitigation                                                                                |
|-------------------------------------------------------|----------|------|------------------------------------------------------------------------------------------|
|CAMEL-AI API breaks between minor versions             |High      |High  |Pin version day one. Read changelog before any upgrade.                                   |
|`process_task()` blocks FastAPI event loop             |High      |High  |Always run in `run_in_executor`. Use `call_soon_threadsafe` for Event bridge.             |
|WSL2 ↔ Windows path confusion                          |High      |Medium|Centralise path normalisation in a single utility module.                                 |
|CAMEL `WorkforceCallback` API undocumented/unstable    |Medium    |Medium|Write an integration test against it before building SSE layer.                           |
|Tauri startup before FastAPI ready                     |Medium    |Low   |Health check on Tauri launch; retry loop with user-visible status.                        |
|BYOK key exposure via logging                          |Low       |High  |Audit all log statements. Never log `os.environ`.                                         |
|`HttpHumanToolkit` breaks CAMEL’s internal message flow|Medium    |High  |Build and test HITL standalone (FastAPI only, no Tauri) before wiring into full workforce.|

-----

## 10. Standalone HITL Proof of Concept (Pre-v1 Gate)

Before building any Tauri UI, validate the HITL loop in isolation:

1. Stand up FastAPI with `/pending`, `/respond`, `/ui` only
1. Subclass `HumanToolkit` → `HttpHumanToolkit`
1. Run a minimal CAMEL workforce (1 coordinator + 1 worker with `HttpHumanToolkit`)
1. Give it a task requiring a clarification question
1. Open `http://localhost:8000/ui` in browser
1. Confirm: agent pauses → question appears in browser → answer submitted → agent continues → result returned

**Pass criteria:** Full round-trip completes without deadlock or event loop conflict. If this works, v1 is unblocked.

-----

## 11. Project File Structure (Proposed)

```
stratum/
├── backend/                    # WSL2 Python package
│   ├── main.py                 # FastAPI app, startup
│   ├── routes/
│   │   ├── task.py             # POST /task
│   │   ├── stream.py           # GET /stream (SSE)
│   │   └── hitl.py             # GET /pending, POST /respond, GET /ui
│   ├── workforce/
│   │   ├── engine.py           # Workforce instantiation, worker config
│   │   ├── callbacks.py        # SSECallback
│   │   └── hitl_toolkit.py     # HttpHumanToolkit
│   ├── workers/
│   │   ├── file_worker.py
│   │   ├── search_worker.py
│   │   └── code_worker.py
│   ├── utils/
│   │   └── paths.py            # WSL2 ↔ Windows path normalisation
│   ├── db/
│   │   └── history.py          # SQLite task history via SQLAlchemy
│   ├── .env                    # BYOK keys — gitignored
│   └── requirements.txt        # Pinned deps including camel-ai==x.x.x
│
├── desktop/                    # Tauri v2 app (Rust + React)
│   ├── src-tauri/              # Rust Tauri backend
│   │   ├── src/main.rs
│   │   └── tauri.conf.json
│   └── src/                    # React frontend
│       ├── App.tsx
│       ├── components/
│       │   ├── TaskInput.tsx
│       │   ├── AgentLog.tsx    # SSE consumer
│       │   └── Artifacts.tsx
│       └── index.css           # Tailwind
│
├── scripts/
│   └── start_backend.sh        # Launch uvicorn in WSL2 (called by Tauri on startup)
│
└── STRATUM_MASTER_CONTEXT.md   # This document
```

-----

## 12. Claude Code Instructions

When using this document as context for Claude Code:

- **Build order:** backend first, Tauri shell second. Validate each layer before the next.
- **First task:** Implement the standalone HITL proof of concept (Section 10) before any other backend work.
- **CAMEL version:** Before any `camel-ai` import, confirm the pinned version in `requirements.txt` and check for breaking changes in that version’s changelog.
- **No closed runtimes:** Do not use Claude Code CLI, Cursor agents, or any closed-vendor tool as part of the agent execution pipeline. CAMEL-AI is the only agent runtime.
- **Path utility first:** Implement `utils/paths.py` before any file I/O code. All file operations go through it.
- **Test the Event bridge:** Before wiring `HttpHumanToolkit` into the full workforce, test `asyncio.Event` + `run_in_executor` + `call_soon_threadsafe` in a minimal script.
- **SQLite for history:** Use SQLAlchemy with SQLite. No external database. File lives in WSL2 home directory.
- **Gitignore `.env` from day one.**

-----

*Document version: 1.0 — May 2026*  
*Author: Tanvir (architect) + Claude (co-author)*  
*Status: Pre-build. Awaiting HITL PoC gate.*