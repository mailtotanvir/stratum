# STRATUM — Execution-First Runtime Rebuild
## Holistic Coding-Agent Build Brief

**Status:** Reset / reconstruction directive  
**Target:** A real local AI execution runtime, not an operator-console simulation  
**Primary objective:** Make the execution spine real first, then make persistence, governance, observability, and replay causally derive from it.

---

# 1. Mission

Rebuild Stratum around one non-negotiable execution spine:

```text
Task
  ↓
Universal AI Adapter
  ↓
Plan
  ↓
Approval
  ↓
Execute
  ↓
Observe
```

The current repository contains substantial prior work: FastAPI APIs, runtime state, sessions, proposals, approvals, governance, decision intelligence, projections, SQLite persistence, SSE, Tauri/React UI, provider abstractions, tool execution, and tests.

The problem is not lack of code.

The problem is that the codebase evolved **top-down around representations of execution before a reliably working execution engine existed**. Much of the existing backend is therefore siloed, stale, speculative, duplicated, or insufficiently connected to real provider calls and real repository work.

Do not preserve architecture merely because it already exists.

The objective of this task is to **analyze the entire existing implementation, salvage only what is genuinely useful, refactor/rewrite aggressively where necessary, and establish a coherent execution-first runtime architecture**.

This is a product rebuild, not a bug-fixing sprint.

---

# 2. Source Architecture — What Must Be Preserved

The existing Stratum architecture documents establish several principles that remain valuable:

- Stratum is a **local-first execution runtime**.
- It is a **repository transformation runtime**.
- The runtime owns execution lifecycle, approvals, persistence, events, artifacts, and human intervention.
- The runtime core should remain small, deterministic, inspectable, composable, and auditable.
- Provider integrations should be adapter-driven and provider-agnostic.
- Agent frameworks should not become the core runtime.
- Tools should be explicit and schema-driven.
- Runtime events are authoritative; projections and derived views are rebuildable.
- Human approval is a first-class execution boundary.
- Skills describe methodology; runtime code implements mechanics.
- Future integrations should be possible without rewriting the runtime foundation.

These principles are consistent with the original architecture documents. In particular, the master context defines Stratum as a local-first execution runtime and repository transformation runtime, with a provider layer and an event-store architecture. fileciteturn1file3L1-L20 fileciteturn1file15L1-L20

The engineering specification defines the intended product outcome as pointing Stratum at a repository, loading engineering context, generating a plan, approving commands/edits, executing transformations, streaming logs, and maintaining history/artifacts. fileciteturn1file2L1-L8

The extensibility addendum explicitly requires an adapter-first, provider-agnostic, UI-agnostic runtime boundary. fileciteturn1file1L1-L20

**Preserve these principles. Do not blindly preserve the current implementation.**

---

# 3. Reset the Mental Model

Do NOT approach this as:

```text
"Fix the existing Stratum backend."
```

Approach it as:

```text
"Reconstruct the actual Stratum runtime using the existing repository as
a source of potentially reusable code and architectural evidence."
```

The current implementation is not authoritative.

The execution contract is authoritative.

If existing modules contradict the execution contract, rewrite them.

If a subsystem cannot be causally connected to real execution, remove it from the critical path.

If a test passes but does not prove a real runtime behavior, do not treat it as evidence of product correctness.

---

# 4. Product Definition

Stratum is a **local execution runtime for AI-assisted engineering work**.

Its fundamental input is:

```text
repository
+
engineering task
+
optional markdown context/specification
+
selected AI provider/model
```

Its fundamental output is:

```text
plan
+
human decision
+
executed actions
+
execution observations
+
artifacts
+
replayable runtime trace
```

The runtime must work without Tauri or React.

A CLI should be sufficient to exercise the complete runtime.

FastAPI may be used as a transport/API adapter, but the execution engine must not depend on HTTP.

Tauri/React must NOT be part of this rebuild's critical path.

---

# 5. First-Class Execution Contract

Implement one coherent runtime API around explicit concepts such as:

```text
Task
Plan
PlanStep
Approval
Execution
Observation
Artifact
RuntimeEvent
```

Do not create dozens of entities merely because the old backend has dozens.

The minimal lifecycle is:

```text
TASK_CREATED
    ↓
PLANNING
    ↓
PLAN_READY
    ↓
APPROVAL_REQUIRED
    ↓
APPROVED / REJECTED
    ↓
EXECUTING
    ↓
OBSERVING
    ↓
COMPLETED / FAILED / CANCELLED
```

Every transition must be caused by an actual runtime action.

There must be no "fake" session, proposal, approval, decision, or timeline record created solely to make a UI look populated.

---

# 6. Universal AI Adapter

This is the most important missing foundation.

Create a stable provider-neutral interface for AI model invocation.

Conceptually:

```python
class AIAdapter(Protocol):
    async def generate(
        self,
        request: AIRequest,
    ) -> AIResponse:
        ...
```

The interface must represent real model interaction, not merely configuration metadata.

At minimum support:

```text
provider
model
messages / prompt
structured response request
streaming capability
tool capability metadata
usage metadata
request/response identifiers
errors
```

The first implementation may use an OpenAI-compatible HTTP/API path because it provides the broadest interoperability.

The adapter must NOT make the core runtime depend on the OpenAI SDK's object model.

The architecture must allow adapters for:

- OpenAI
- Anthropic
- OpenAI-compatible gateways
- OpenRouter
- local inference / Ollama
- future providers

without changing the runtime execution engine.

The provider layer should answer:

> "How do I communicate with this AI system?"

The runtime should answer:

> "What do I do with the AI result?"

Never mix those responsibilities.

---

# 7. Real Planning

The first real intelligent operation must be:

```text
Task
  ↓
Repository/context inspection
  ↓
AI adapter
  ↓
Structured Plan
```

The AI must return a structured plan, not merely prose.

A plan should contain explicit steps, for example:

```text
Plan
  id
  task_id
  rationale
  steps[]

PlanStep
  id
  description
  action_type
  proposed_operation
  risk
  requires_approval
```

For the first implementation, support a deliberately small action vocabulary.

Example:

```text
read_file
write_file
run_command
```

Do not build a huge tool ecosystem before these work.

---

# 8. Approval Is a Runtime Boundary

Approval must happen between planning and side effects.

The invariant is:

```text
NO APPROVAL
    =
NO SIDE EFFECT
```

The CLI must display the actual generated plan and ask the human to approve it.

Approval must be represented as a real runtime decision and emitted as an authoritative event.

Example:

```text
Plan generated:

1. Read README.md
2. Modify example.py
3. Run pytest

Approve plan? [y/N]
```

The executor must not be reachable from an unapproved plan.

Do not simulate approval in tests unless there is also a real integration test proving the actual approval boundary.

---

# 9. Real Execution

Execution must perform real work against a real local repository.

The first benchmark should be intentionally tiny.

Example:

```text
Repository:
  a temporary git repository

Task:
  "Change the greeting returned by hello.py from Hello to Hello Stratum."
```

The AI generates a plan.

The operator approves it.

The runtime performs the actual file modification.

Then the runtime runs a real verification command.

Then the runtime reports the actual result.

The acceptance condition is not:

```text
"executor returned success"
```

It is:

```text
the repository actually changed as requested
AND
the verification command actually ran
AND
the resulting observations were recorded.
```

---

# 10. Runtime Events — Redpanda / Kafka

Replace the current conceptual event approach with a proper event boundary that can support local Kafka-compatible infrastructure.

Use **Redpanda** as the local Kafka-compatible event broker.

The runtime must have a small event-publishing abstraction:

```text
Runtime
   ↓
Event Publisher
   ↓
Redpanda / Kafka
```

Do not scatter Kafka calls throughout the runtime.

Define an explicit event contract.

Every meaningful execution transition should emit a structured event such as:

```text
task.created
task.planning_started
ai.requested
ai.responded
plan.generated
approval.requested
approval.granted
approval.rejected
execution.started
tool.started
tool.completed
tool.failed
artifact.created
observation.recorded
task.completed
task.failed
```

Events must include enough metadata for reconstruction:

```text
event_id
event_type
event_version
task_id
execution_id
timestamp
sequence
producer
payload
correlation_id
causation_id
```

Use deterministic identifiers and ordering semantics.

The event stream is not merely a logging stream.

It is the authoritative runtime history.

---

# 11. Event Sourcing / Replay

Implement the runtime so that an execution can be reconstructed from its event history.

The minimum requirement is:

```text
Run task
  ↓
events written to Redpanda
  ↓
execution completes
  ↓
replay events
  ↓
reconstruct execution history/state
```

Replay must not invoke the LLM or repeat side effects.

Replay means:

```text
read historical events
→ rebuild state
→ reproduce the recorded execution narrative
```

This distinction is mandatory.

If useful, maintain a small local durable event index/store alongside Redpanda, but do not create a second competing source of truth.

The architecture documents explicitly state that runtime events are authoritative and derived projections must be rebuildable. fileciteturn1file15L1-L20

---

# 12. Kafka Topic Strategy

Keep the initial topic topology small.

Start with one canonical runtime topic:

```text
stratum.runtime.events.v1
```

Optionally introduce separate topics only when there is a demonstrated need.

Partitioning should preserve ordering for a single execution/task using a stable key such as:

```text
execution_id
```

The event contract must be versioned from day one.

Do not prematurely build a distributed event architecture.

The goal is:

```text
local runtime
+
local Redpanda
+
durable ordered events
+
replay
```

not:

```text
enterprise Kafka platform
```

---

# 13. Event Consumer

Build at least one real consumer.

For the initial product, a local observer/CLI consumer is sufficient:

```text
Redpanda
   ↓
Runtime Event Consumer
   ↓
human-readable execution trace
```

Example:

```text
12:01:04 task.created
12:01:05 ai.requested
12:01:08 ai.responded
12:01:08 plan.generated
12:01:09 approval.requested
12:01:15 approval.granted
12:01:16 execution.started
12:01:16 tool.started write_file
12:01:16 tool.completed write_file
12:01:17 tool.started pytest
12:01:20 tool.completed pytest
12:01:20 task.completed
```

This is the first real observability product.

No dashboard is required.

---

# 14. Repository Context

Implement a small, deterministic repository context loader.

It should be capable of:

- validating a repository path
- detecting git
- reading selected files
- reading Markdown context/specification
- producing bounded context for the AI adapter

Do NOT dump an entire repository into the model.

The context builder must be explicit and bounded.

At minimum support:

```text
repository metadata
git status
file tree summary
selected text files
explicit context markdown
```

The AI should receive enough information to make a useful first plan without blindly reading hundreds of files.

---

# 15. Tool Execution Boundary

Create an explicit tool interface.

Conceptually:

```text
Tool
 ├── name
 ├── description
 ├── input_schema
 ├── risk_level
 └── execute()
```

Initial tools:

```text
read_file
write_file
run_command
```

Each invocation produces events before and after execution.

Example:

```text
tool.started
tool.completed
```

or:

```text
tool.started
tool.failed
```

Tool execution must be isolated from planning.

The AI proposes.

The runtime validates.

The approval policy decides.

The executor performs.

---

# 16. Safety

For repository mutation:

- require a git repository where practical
- capture initial git status
- preserve a rollback reference
- never silently overwrite unrelated changes
- enforce repository/workspace boundaries
- require approval for mutation/destructive operations
- record every side effect as an event

Do not implement a massive governance framework.

Implement the minimum real safety boundary required for the execution engine.

---

# 17. Governance — Rebuild It Around Reality

The existing governance code should be treated as a candidate source of reusable policy logic, not as the authority.

Governance should answer real questions:

```text
Is this operation allowed?
Does it require approval?
Was approval granted?
What actually happened?
```

Do NOT preserve governance objects that have no real execution producer.

A proposal must correspond to an actual AI-generated plan/action.

An approval must correspond to an actual pending operation.

A governance event must correspond to an actual runtime event.

If those causal relationships cannot be established, delete or quarantine the subsystem.

---

# 18. Persistence

Do not immediately recreate the existing large SQLite model.

Start with the authoritative event stream.

If SQLite is retained, it should be clearly defined as:

```text
local event index / cache / projection
```

unless there is a compelling reason for it to be authoritative.

Avoid recreating dozens of tables.

The architecture should allow:

```text
Redpanda event log
       ↓
replay
       ↓
derived runtime state
```

The existing master architecture already states that projections are derived/rebuildable and must not become the sole location of critical runtime facts. fileciteturn1file15L1-L20

---

# 19. FastAPI

FastAPI is a transport adapter, not the runtime.

If retained, it should expose a thin API over the runtime:

```text
POST /tasks
GET  /tasks/{id}
POST /tasks/{id}/approve
POST /tasks/{id}/reject
GET  /tasks/{id}/events
```

The runtime must work without FastAPI.

The CLI must be able to exercise the exact same runtime.

This eliminates the previous failure mode where the backend became a large application whose HTTP endpoints were mistaken for proof that the runtime worked.

---

# 20. CLI

The CLI is the first product surface.

It must be capable of:

```bash
stratum run \
  --repo ./example-repo \
  --task "Change the greeting returned by hello.py"
```

The operator should see:

```text
Repository validated.

Planning...

PLAN
1. Read hello.py
2. Modify hello.py
3. Run pytest

Approve? [y/N]
```

After approval:

```text
Executing...

✓ read_file
✓ write_file
✓ pytest

Task completed.

Replay:
stratum replay <execution-id>
```

This is the first genuine Stratum product.

---

# 21. No Tauri / React Yet

Do not make the existing Tauri/React application part of the acceptance path.

Do not spend time repairing operator-console UI.

Do not add new UI panels.

Do not make the desktop shell a dependency of the runtime.

Once the CLI execution path is proven, the UI becomes a client of a real runtime instead of a simulation surface.

The architecture documents describe UI/transport as a layer above the runtime; preserve that separation. fileciteturn1file3L1-L20

---

# 22. Existing Codebase Analysis — Required Before Major Changes

Before implementing the rebuild:

1. Map the existing repository.
2. Identify actual executable paths.
3. Identify real provider integrations.
4. Identify existing tool implementations.
5. Identify proposal/approval logic that can be reused.
6. Identify event schemas and persistence.
7. Identify duplicate/stale implementations.
8. Identify tests that exercise real external/runtime behavior.
9. Identify mocks/stubs/fake projections.
10. Identify code that exists only to serve the old operator UI.

Produce a concise architectural assessment:

```text
KEEP
REWRITE
DELETE
QUARANTINE
```

Do not preserve code merely because it has tests.

Do not delete useful implementation blindly.

Do not spend enormous token budgets repeatedly reading every file after the initial inventory. Establish the dependency graph and focus analysis on execution-critical paths.

---

# 23. Test Philosophy — Change the Definition of "Passing"

Unit tests are necessary but insufficient.

The most important test is a real local vertical integration test:

```text
real task
→ real repository
→ real AI adapter
→ real structured plan
→ real approval
→ real tool execution
→ real repository mutation
→ real verification command
→ real Redpanda events
→ real event replay
```

At least one acceptance test must run against:

- an actual local repository fixture
- an actual configured AI provider
- a real local Redpanda instance
- actual filesystem effects
- actual subprocess execution

No fake provider response may be substituted for the primary acceptance path.

Mocks may exist for fast unit tests, but they cannot constitute evidence that the product works.

---

# 24. Provider Test

The first provider acceptance test must prove:

```text
Stratum
  ↓
AIAdapter
  ↓
real provider API
  ↓
real model response
  ↓
structured Plan
```

The test should use a small deterministic engineering task.

Record provider/model/request metadata in runtime events, but NEVER record API secrets.

---

# 25. Redpanda Test

The first event acceptance test must prove:

```text
runtime action
  ↓
producer
  ↓
Redpanda
  ↓
consumer
  ↓
recorded event
  ↓
replay
  ↓
same execution history
```

Do not call a logger "an event system."

Do not call an in-memory list "event sourcing."

The acceptance test must cross the actual producer/consumer boundary.

---

# 26. First End-to-End Benchmark

Create a disposable fixture repository:

```text
example-repo/
  hello.py
  test_hello.py
```

Initial behavior:

```python
def greeting():
    return "Hello"
```

Task:

```text
Change the greeting to "Hello Stratum" and update the test accordingly.
```

The expected real flow is:

```text
Task
 ↓
Context loader
 ↓
AI adapter
 ↓
Structured plan
 ↓
Approval
 ↓
read_file
 ↓
write_file
 ↓
write_file
 ↓
pytest
 ↓
Observation
 ↓
Events in Redpanda
 ↓
Replay
```

Expected final state:

```text
pytest passes
git diff shows the intended changes
execution is marked completed
all important lifecycle events exist
replay reconstructs the execution
```

This benchmark is the definition of "Stratum works."

---

# 27. Architecture Target

The resulting architecture should look approximately like:

```text
                         ┌─────────────────────┐
                         │   CLI / FastAPI      │
                         │     / future UI      │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   Runtime Engine     │
                         │                     │
                         │ Task                 │
                         │ Planner              │
                         │ Approval             │
                         │ Executor             │
                         │ Observation          │
                         └───────┬───────┬─────┘
                                 │       │
                    ┌────────────┘       └────────────┐
                    ▼                                 ▼
             ┌──────────────┐                 ┌──────────────┐
             │ Universal AI │                 │ Tool Runtime │
             │   Adapter    │                 │              │
             └──────┬───────┘                 │ filesystem   │
                    │                         │ shell        │
          ┌─────────┼──────────┐              │ git          │
          ▼         ▼          ▼              └──────────────┘
       OpenAI   Anthropic   Compatible
       /etc.       /etc.      APIs

                         Runtime Events
                               │
                               ▼
                       ┌─────────────────┐
                       │    Redpanda     │
                       │ Kafka-compatible│
                       └────────┬────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
              Event Consumer            Replay Engine
                    │                       │
                    ▼                       ▼
               Live trace             Reconstructed state
```

The runtime engine is the center.

Everything else is an adapter, execution mechanism, or derived consumer.

---

# 28. Scalability Rules

This rebuild must be small without being a toy.

Design stable seams for:

```text
AIAdapter
EventPublisher
EventConsumer
Tool
ApprovalPolicy
ExecutionStore / Replay
Transport
```

But do not implement speculative adapters.

One real implementation per seam is sufficient initially.

For example:

```text
AIAdapter
  └── OpenAICompatibleAdapter

EventPublisher
  └── RedpandaPublisher

EventConsumer
  └── RedpandaConsumer

Transport
  └── CLI
```

Later:

```text
AIAdapter
  ├── OpenAI
  ├── Anthropic
  ├── OpenRouter
  ├── Ollama
  └── ...

Transport
  ├── CLI
  ├── FastAPI
  └── Tauri
```

The interfaces are the scalable part.

The implementation should remain small.

---

# 29. Explicit Anti-Goals

Do NOT:

- rebuild the 20 operator-console panels
- repair stale dashboard endpoints merely because they exist
- add another projection
- add another database model without a runtime requirement
- create fake sessions
- create fake proposals
- create fake decision intelligence
- create mock execution flows as the primary acceptance test
- add Tauri functionality
- add React functionality
- build a large agent framework
- build multi-agent orchestration
- build RAG
- build vector memory
- build autonomous recursion
- build distributed workers
- build Kubernetes/Docker infrastructure
- create an abstraction for every possible future provider
- make FastAPI required for execution
- treat passing pytest counts as product validation

The project must not return to infrastructure-first development.

---

# 30. Definition of Done

This rebuild is successful when a fresh checkout can demonstrate:

```text
$ stratum run --repo ./example-repo \
    --task "Change Hello to Hello Stratum"

Planning...
AI provider responded.

PLAN
...

Approval required.
Approve? y

Executing...
✓ file read
✓ file modified
✓ test executed

Task completed.

Execution ID: ...

$ stratum replay <execution-id>

Replaying...
✓ task created
✓ plan generated
✓ approval granted
✓ tools executed
✓ verification completed
✓ task completed
```

And independently:

```text
Redpanda contains the authoritative runtime events
```

and:

```text
replay reconstructs the recorded execution
without invoking the AI or repeating side effects.
```

Only after this works should existing governance, projections, observability dashboards, Tauri, and richer UI be reconsidered.

---

# 31. Agent Operating Mode

You are acting as the principal engineer performing a product reconstruction.

Do not optimize for number of files changed.

Do not optimize for preserving previous code.

Do not optimize for test-count growth.

Optimize for:

```text
causal correctness
execution correctness
architectural coherence
provider neutrality
event durability
replayability
human approval
real repository transformation
```

When an old subsystem conflicts with these objectives, remove or rewrite it.

When uncertain whether old code is useful, inspect its actual callers and runtime behavior rather than assuming its purpose from filenames.

Do not repeatedly scan the entire repository after the initial architectural inventory. Build a dependency map and work from the execution-critical graph.

---

# 32. Required Deliverables

At completion, provide:

1. Reconstructed runtime architecture.
2. Working universal AI adapter.
3. Working real provider integration.
4. Working structured planner.
5. Working approval gate.
6. Working tool execution boundary.
7. Working repository transformation benchmark.
8. Working Redpanda producer.
9. Working Redpanda consumer.
10. Working event replay.
11. Minimal CLI.
12. Thin FastAPI adapter if useful and stable.
13. Tests including the real vertical acceptance test.
14. Updated architecture documentation.
15. Migration/deletion notes describing what old Stratum code was removed, retained, or quarantined.
16. A concise README showing how to run the complete local system.

---

# 33. Final Architectural Principle

The runtime must make the following statement true:

> **Nothing is observable until something has actually happened.**

And:

> **Nothing can be approved unless something has actually been proposed.**

And:

> **Nothing can be proposed unless a real AI/provider interaction produced it.**

And:

> **Nothing can be executed unless it passed the approval boundary.**

And:

> **Every meaningful execution transition produces a durable event that can be replayed.**

Therefore:

```text
                    REALITY
                       │
                       ▼
Task → AI → Plan → Approval → Execute
                                  │
                                  ▼
                              Observe
                                  │
                                  ▼
                              Redpanda
                                  │
                                  ▼
                                Replay
```

This is the new Stratum.

Build this spine first.

Everything else is downstream.
