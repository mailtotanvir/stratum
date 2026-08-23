# Stratum Runtime

**A local-first execution runtime for AI-assisted engineering work.**

Stratum turns a repository + a task into a structured plan, puts a human
approval gate between planning and any side effect, executes the approved
plan with real tools against the real filesystem, records every transition
as durable events, and replays the whole execution from that event history.

```text
Task -> AI Adapter -> Plan -> Approval -> Execute -> Observe -> Events -> Replay
```

This is the execution spine. There is no dashboard, no simulated state, and
no observable record of anything that did not actually happen.

---

## Install

Requires Python 3.11+.

```bash
cd stratum
uv venv .venv && uv pip install -e '.[dev,api]'   # or: pip install -e '.[dev,api]'
```

## Configure a provider

The AI adapter speaks the OpenAI-compatible `/chat/completions` dialect
(OpenAI, Azure OpenAI, OpenRouter, Groq, Ollama, vLLM, ...). Credentials are
resolved as matched pairs:

```bash
# explicit (highest precedence)
export STRATUM_PROVIDER_BASE_URL=https://api.groq.com/openai/v1
export STRATUM_PROVIDER_API_KEY=gsk_...
export STRATUM_MODEL=openai/gpt-oss-20b
# or rely on an existing GROQ_API_KEY / OPENAI_API_KEY (+ OPENAI_API_BASE)
```

Check your setup:

```bash
stratum doctor
```

## Run the benchmark

```bash
# one-time: make the fixture repo a git repo (already committed in-tree)
git -C example-repo log >/dev/null || (git -C example-repo init && git -C example-repo add -A && git -C example-repo commit -m init)

stratum run \
  --repo ./example-repo \
  --task 'Change the greeting returned by hello.py from "Hello" to "Hello Stratum" and update the test accordingly.' \
  --file hello.py --file test_hello.py
```

What you will see:

```text
Repository validated.

Planning...

PLAN
  1. [read_file] Read current hello.py (hello.py)
* 2. [write_file] Write updated hello.py ...        (* = mutates repo)
  3. [run_command] Run tests ...

Approve plan for exe_...? [y/N] y

Executing...
  [+] read hello.py (86 bytes)
  [+] updated hello.py (94 chars)
  [+] `python -m pytest -q` exited 0

Task COMPLETED.
Execution ID: exe_mt4oq87s-kkrlpg49
```

Answering `n` rejects the plan; nothing is ever written without approval.
The invariant is structural: the executor is unreachable until an approval
decision has been recorded for the pending plan.

## Replay an execution

```bash
stratum replay <execution-id>
```

Rebuilds the full narrative from recorded events — **no AI calls, no side
effects**:

```text
Execution exe_mt4oq87s-kkrlpg49
  Task:     Change the greeting ...
  Plan (5 steps): ...
  Approval: granted by cli-operator
  [+] 18:01:38 read_file - read hello.py (86 bytes)
  [+] 18:01:38 write_file - updated hello.py (94 chars)
  [+] 18:01:38 run_command - `pytest -q` exited 0
  artifact: hello.py (94 bytes)
  Status:   COMPLETED

(26 events replayed; no AI calls, no side effects)
```

## Event streaming with Redpanda (optional but recommended)

Events are always written to a local SQLite database
(`$STRATUM_DATA_DIR/stratum.db`, default `./.stratum-data/`) — a queryable
event index plus an execution-state projection. That projection is what lets
the engine survive restarts: pending approvals are rehydrated on startup, so
you can approve a plan submitted before a crash or restart.

To also publish events to Redpanda — the
authoritative stream — run a broker locally:

```bash
docker compose -f docker-compose.redpanda.yml up -d   # from the repo root
export STRATUM_KAFKA_BROKERS=127.0.0.1:9092
```

Then every `stratum run` publishes each event to topic
`stratum.runtime.events.v1`, keyed by `execution_id` so a single execution's
history stays totally ordered in one partition.

Live trace consumer:

```bash
stratum consume --follow      # human-readable line per event
stratum replay <id>           # prefers broker history, falls back to local DB
```

Broker round-trip acceptance test (skipped automatically when no broker):

```bash
STRATUM_KAFKA_BROKERS=127.0.0.1:9092 pytest tests/acceptance/test_redpanda.py
```

## Browser console (UAT)

```bash
# with Redpanda running:
docker compose -f ../docker-compose.redpanda.yml up -d   # from repo root
stratum serve --port 8899 --brokers 127.0.0.1:9092
# or journal-only (no broker):
stratum serve --port 8899
```

Open **http://127.0.0.1:8899** — submit a task, watch the plan arrive,
press **Approve & execute** (or Reject), observe the live event timeline,
then replay any run from the history panel. The console is a plain static
page served by the FastAPI adapter; it is just another client of the same
engine, holds no state of its own, and binds to 127.0.0.1 only.

## HTTP transport (optional)

The same engine is available over a thin FastAPI adapter:

```python
from stratum.adapters.openai_compatible import OpenAICompatibleAdapter
from stratum.api import RuntimeHolder, create_app
from stratum.approval import InteractiveApprovalPolicy  # or your own policy
from stratum.config import resolve_provider
from stratum.engine import StratumRuntime
from stratum.journal import FileEventJournal, JournalPublisher
from stratum.planning import Planner
from stratum.publisher import CompositeEventPublisher

cfg = resolve_provider()
journal = FileEventJournal(".stratum-data/events.ndjson")
holder = RuntimeHolder(
    runtime=StratumRuntime(
        adapter=OpenAICompatibleAdapter(base_url=cfg.base_url, api_key=cfg.api_key),
        model=cfg.model,
        publisher=CompositeEventPublisher(JournalPublisher(journal)),
        approval_policy=InteractiveApprovalPolicy(),
        planner=Planner(model=cfg.model),
    ),
    read_events=journal.read_execution,
)
app = create_app(holder)   # uvicorn module:app
```

Routes: `POST /tasks`, `GET /tasks/{id}`, `POST /tasks/{id}/approve`,
`POST /tasks/{id}/reject`, `GET /tasks/{id}/events`, `GET /tasks/{id}/replay`.

## Architecture in one screen

```text
                     CLI / FastAPI / future UI
                                |
                        Runtime Engine
        Task | Planner | Approval | Executor | Observation
                   |                    |
            Universal AI Adapter    Tool Runtime
            (openai-compatible)     read_file write_file run_command
                   |                    |
              providers ...        workspace boundary + git safety
                                |
                         Runtime events
                                |
                    Redpanda  +  local journal
                                |
                    ------------+------------
                    |                       |
              live consumer             replay engine
```

Seams (one real implementation each): `AIAdapter`, `EventPublisher`,
`Tool`, `ApprovalPolicy`, transports. See `ARCHITECTURE.md` for the full
contract and `../MIGRATION.md` for what happened to the old codebase.

## Safety model

- Repository mutations require a plan step flagged `requires_approval`
  (forced for `write_file` and `run_command`) and a granted approval event.
- Tools resolve paths strictly inside the target workspace; escapes are
  refused.
- Initial git branch/HEAD/status are captured at task creation as the
  rollback reference.
- Every tool invocation emits `tool.started` + `tool.completed|failed`;
  every file write emits an `artifact.created` event with sha256 + diff.
- API keys are never written into events.

## Is it really calling an LLM?

Yes. Proof you can run yourself:

```bash
# 1. Every AI call is recorded with provider-issued request ids and token usage:
sqlite3 .stratum-data/stratum.db \
  "SELECT payload_json FROM events WHERE event_type='ai.responded' ORDER BY rowid DESC LIMIT 1;"

# 2. Negative control — a bad key fails against the LIVE provider:
STRATUM_PROVIDER_API_KEY=bogus stratum run --repo ./example-repo --task t
# -> provider returned 401: invalid_api_key   (a mock cannot emit this)
```

The deterministic `ScriptedAdapter` exists only under `tests/`; production
paths use the httpx OpenAI-compatible adapter exclusively.

## Tests

```bash
pytest                      # unit + vertical integration (scripted provider)
pytest tests/acceptance     # adds REAL-provider acceptance when configured
```

The vertical tests exercise a real disposable git repository, real file
mutations, real subprocess verification, and the real event journal/replay
path. The acceptance suite proves the same spine against a live provider
and, when available, a live Redpanda.
