# Stratum Runtime Architecture (v2 — execution-first rebuild)

Status: authoritative for `stratum/` package
Supersedes: the pre-rebuild backend architecture in `../backend/` (quarantined)

---

## 1. The spine

One lifecycle, driven only by real actions:

```text
TASK_CREATED -> PLANNING -> PLAN_READY -> APPROVAL_REQUIRED
    -> APPROVED | REJECTED -> EXECUTING -> OBSERVING
        -> COMPLETED | FAILED | CANCELLED
```

Invariants (enforced in `engine.py`, not by convention):

1. Nothing is observable until something actually happened.
2. Nothing can be approved unless something was actually proposed
   (`decide_and_execute` is guarded on `APPROVAL_REQUIRED` and on a matching
   pending `plan_id`).
3. Nothing can be proposed unless a real provider interaction produced it
   (plans are parsed from real adapter responses; parse failures fail the
   task before approval).
4. Nothing can be executed unless it passed the approval boundary.
5. Every meaningful transition emits a durable event.

## 2. Modules

| Module | Responsibility |
|---|---|
| `events.py` | RuntimeEvent contract (v1), 17-type vocabulary, per-execution sequence + correlation/causation chain |
| `publisher.py` | EventPublisher protocol; InMemory (tests only); Composite fan-out |
| `store.py` | SQLite local event index + execution-state projection (2 tables, WAL, stdlib) |
| `journal.py` | NDJSON durable local event index (write + read) |
| `redpanda.py` | The only module that talks Kafka: producer, reader, topic ensure; events keyed by `execution_id` |
| `ai.py` | AIAdapter protocol, AIRequest/AIResponse — no SDK types leak inward |
| `adapters/openai_compatible.py` | httpx-based /chat/completions adapter (OpenAI/Azure/OpenRouter/Groq/Ollama/vLLM) |
| `adapters/scripted.py` | Deterministic canned adapter — tests/offline ONLY, never acceptance evidence |
| `context.py` | Bounded repo context: git info, depth-limited tree, selected files, operator markdown, char budget |
| `planning.py` | Plan/PlanStep models, strict JSON schema prompt, hard validation of model output |
| `materialize.py` | Grounded write materialization: one extra real provider call using actual read contents |
| `tools.py` | Tool boundary: read_file / write_file / run_command, workspace path containment, diffs, sha256 |
| `approval.py` | ApprovalPolicy protocol; InteractiveApprovalPolicy (product default); PreDecided (tests only) |
| `engine.py` | StratumRuntime orchestrator; state guards; event emission; fail-stop execution |
| `replay.py` | Pure event fold -> ReplayedExecution + narrative renderer + trace-line formatter |
| `cli.py` | run / replay / consume / doctor |
| `api.py` | Thin FastAPI transport over the same engine |

## 3. Event contract

Topic: `stratum.runtime.events.v1`. Key: `execution_id` (single-partition
ordering per execution). Envelope fields:

```text
event_id, event_type, event_version(=1), task_id, execution_id,
timestamp(UTC ISO-8601 ms), sequence(per-execution, monotonic from 1),
producer("stratum-runtime"), payload, correlation_id, causation_id
```

Vocabulary v1:

```text
task.created task.planning_started ai.requested ai.responded plan.generated
approval.requested approval.granted approval.rejected execution.started
tool.started tool.completed tool.failed artifact.created observation.recorded
task.completed task.failed task.cancelled
```

Rules:
- Events are facts; they are never rewritten.
- `sequence` orders within an execution; `causation_id` chains each event to
  its immediate predecessor; `correlation_id` is shared by one task lineage.
- Provider/model/request metadata may be recorded; secrets must not.
- The broker stream is authoritative when configured. The journal is an
  explicitly non-authoritative local index/cache used for offline replay.

## 4. Execution semantics

Planning: bounded context + strict-JSON instructions -> provider ->
validated Plan. Invalid output = `task.failed` before approval exists.

Approval: engine consults the policy between planning and side effects.
CLI uses an interactive y/N prompt; HTTP transport passes explicit records;
tests use a pre-decided policy (never as acceptance evidence).

Execution: steps run sequentially, fail-stop. Each step emits
tool.started/completed|failed plus observation.recorded; file writes emit
artifact.created with unified diff + sha256s. A mutating command that runs
but exits non-zero fails the task (the command still ran — events say so).

Write materialization: if a write_file step carries intent but no concrete
bytes, the runtime performs exactly one additional real provider call,
grounded in the file content recorded by the preceding read step. Both AI
calls are visible in the event stream (`purpose=planning`,
`purpose=materialize_write`).

Replay: pure fold of persisted events. No provider calls. No tool effects.

## 3b. Persistence model

Choice: **SQLite** (stdlib, file-based, zero ops) — matches the local-first
principle; Postgres would add an operational dependency with no benefit at
this scale.

Exactly two tables (`store.py`, schema-versioned via `PRAGMA user_version`):

```text
events     — queryable local index of the authoritative stream
             (idempotent by event_id; ordered by execution_id, sequence)
executions — state projection: status, plan_json, error, decider,
             created/updated timestamps, last_event_sequence watermark,
             correlation_id
```

Source-of-truth rules (unchanged):
- Broker configured -> Redpanda is authoritative; SQLite is cache/index.
- No broker -> SQLite is the persistence boundary of last resort.
- Every row is derivable from events; nothing here contradicts the stream.

What durability buys the engine:
- Every `_emit` also indexes the event (thread-offloaded writes).
- Every lifecycle transition projects into `executions`.
- `resume_pending()` hydrates APPROVAL_REQUIRED executions from the store
  after a process restart: plan, task metadata, sequence watermark and
  correlation id are restored, so `decide_and_execute` works exactly as
  before the crash. Resumed executions never call the provider again
  (asserted in tests); write materialization re-grounds in current file
  contents if the scratch read-cache was lost mid-execution.

## 5. Deliberate limits

Small on purpose until each layer earns growth:

- Action vocabulary: `read_file`, `write_file`, `run_command`.
- One topic. One partition key. One consumer.
- One provider dialect (OpenAI-compatible). New providers = new adapters,
  zero core changes.
- CLI is the product surface; FastAPI is optional sugar; UI comes later as
  just another client.

## 6. Acceptance definition

"Stratum works" means all of these against REAL infrastructure:

1. Real repository mutated as requested (git diff shows it).
2. Verification command actually ran (exit code recorded).
3. Full lifecycle event chain persisted.
4. Replay reconstructs the execution without AI or effects.
5. Provider metadata recorded, secrets absent.
6. Broker round trip preserves ordering and replays identically
   (env-gated test).
