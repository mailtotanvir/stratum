# Stratum

**A local-first AI execution runtime for repository transformation.**

Stratum turns `repository + task` into a structured plan, puts a **human
approval gate** between planning and any side effect, executes approved plans
with real tools against real files, records every transition as durable
events (Redpanda/Kafka + SQLite), and replays executions from that event
history.

```text
Task → AI Adapter → Plan → Approval → Execute → Observe → Events → Replay
```

Nothing is observable until something actually happened. Nothing can be
approved unless something was proposed by a real provider interaction.
Nothing can be executed unless it passed the approval boundary.

---

Runtime docs: **[stratum/README.md](./stratum/README.md)** ·
Architecture: **[stratum/ARCHITECTURE.md](./stratum/ARCHITECTURE.md)** ·
Migration notes: **[MIGRATION.md](./MIGRATION.md)**
## Manual quick start

```bash
cd stratum
uv venv .venv && uv pip install -e '.[dev,api]'
source .venv/bin/activate

# provider (OpenAI-compatible; matched key+url pairs resolved automatically:
# GROQ_API_KEY, or OPENAI_API_KEY [+ OPENAI_API_BASE], or STRATUM_PROVIDER_*)
export GROQ_API_KEY=...

# broker (optional but recommended)
docker compose -f docker-compose.redpanda.yml up -d

stratum run --repo ./example-repo \
  --task 'Change the greeting returned by hello.py from "Hello" to "Hello Stratum" and update the test accordingly.' \
  --file hello.py --file test_hello.py \
  --brokers 127.0.0.1:9092
```

## Is it really calling an LLM?

Yes — and the runtime is built so you can prove it:

- Every AI interaction emits `ai.requested` / `ai.responded` events with the
  endpoint host, model id, the provider's own request id (`chatcmpl-…`),
  token usage, and latency — queryable in SQLite and Redpanda.
- Negative control: run any task with a bad key
  (`STRATUM_PROVIDER_API_KEY=bogus stratum run --repo ./example-repo --task t`)
  and the live provider rejects with its own `401 invalid_api_key`.
- The deterministic mock adapter exists only under `tests/`; production paths
  (`cli`, `serve`, `engine`) use the httpx OpenAI-compatible adapter only.

## What's in this repository

| Path | Description |
|---|---|
| `stratum/` | **The v2 execution-first runtime** (engine, universal AI adapter, tools, approval gate, Redpanda transport, SQLite persistence, replay, CLI, browser console) |
| `MIGRATION.md` | Keep/rewrite/quarantine verdicts from the v1 → v2 rebuild |
| `STRATUM_EXECUTION_FIRST_REBUILD.md` | The rebuild directive that drove v2 |
| `docs/` | Historical architecture/spec documents |
| `backend/`, `desktop/` | ⚠️ **Quarantined v1 code** (FastAPI operator-console backend + Tauri shell). Kept for reference only — not on any runtime path; see [MIGRATION.md](./MIGRATION.md) |
| `docker-compose.redpanda.yml` | Local Kafka-compatible event broker |

## Architecture in one screen

```text
                 CLI / Browser console / FastAPI
                              │
                       Runtime Engine
      Task │ Planner │ Approval │ Executor │ Observation
                    │                    │
             Universal AI Adapter    Tool Runtime
             (OpenAI-compatible)     read_file write_file run_command
                    │                    │
        OpenAI / Azure / Groq /     workspace boundary + git safety
        OpenRouter / Ollama …
                              │
                  Runtime events (17-type contract, v1)
                              │
                  Redpanda  +  SQLite index/projection
                              │
                  ┌───────────┴───────────┐
            live consumer            replay engine
```

Seams with one real implementation each: `AIAdapter`, `EventPublisher`,
`Tool`, `ApprovalPolicy`, transports. New providers or transports require
zero core changes.

## Safety model

- Mutating steps are forced `requires_approval`; executor is structurally
  unreachable without a recorded human decision.
- Tools resolve paths strictly inside the target workspace.
- Git branch/HEAD/status captured as rollback reference at task creation.
- Every tool call wrapped in `tool.started/completed/failed`; every file
  write produces an artifact event with sha256 + unified diff.
- Secrets never appear in events (asserted in tests).

## Status

- v2 execution spine: working, tested end-to-end against live providers and
  live Redpanda (`pytest` acceptance suite; `tests/acceptance/`).
- v1 console backend/desktop: quarantined pending deletion.
