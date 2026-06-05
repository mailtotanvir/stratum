# ADR: Tool Registry and Tool Invocations

## Status

Accepted for Stratum v1 runtime boundary plumbing.

## Context

Stratum now has registered tools and tool invocation records.

Tool registration describes available capabilities. A `ToolRecord` names a tool,
stores its description, enabled state, and parameter schema. It does not provide
an executable implementation.

Tool invocation records describe runtime intent and state. A
`ToolInvocationRecord` records that a runtime session intends to use a registered
tool, plus the invocation status and JSON payloads.

## Current Semantics

Registering a tool does not implement execution.

Creating a tool invocation does not execute a tool. The current API creates a
`ToolInvocationRecord` and immediately marks it `running`. This mirrors the
future lifecycle shape without calling a shell, mutating the filesystem, invoking
MCP, calling an LLM, or running any adapter.

Tool invocation status tracks:

- `requested`
- `running`
- `completed`
- `failed`

Immediate `requested` to `running` transition is temporary. Once Stratum has a
`ToolExecutionAdapter`, the runtime can create an invocation, run governance
checks, hand execution to the adapter, and then transition the invocation to
`completed` or `failed`.

## Why Durable Tool Invocation Records

Durable invocation records give Stratum:

- auditability of attempted tool use
- replayability for reconstruction and debugging
- a place for future governance checks before execution
- a durable anchor for future artifact linkage
- a path to execution isolation
- a queryable surface for future UI/operator inspection

## State Separation

Tool state is separated across durable records:

- `ToolRecord` is the capability definition.
- `ToolInvocationRecord` is an attempted use of that capability.
- `RuntimeSessionRecord` is the execution attempt that owns the invocation.
- `ArtifactRecord` is a durable output or referenced artifact.
- `RuntimeEvent` is the append-only source of truth for observed state changes.

```text
RuntimeSessionRecord
        |
        | owns attempted use
        v
ToolInvocationRecord ---- references ----> ToolRecord
        |
        | future execution may produce
        v
ArtifactRecord

RuntimeEvent records each lifecycle transition.
```

## Tool Execution Artifact Semantics

`ToolExecutionResult` may include adapter-declared artifacts. These artifacts are
declarations of outputs, not filesystem writes. `ToolExecutionService` registers
declared artifacts as `ArtifactRecord` rows.

This layer is registry-only persistence:

- no files are created by this layer
- `ArtifactRecord` records path, kind, and metadata only
- actual file-writing tools will be added later behind real adapters

Created artifacts are attached to the invocation's task and runtime session when
available. `RuntimeArtifactLinkRecord` links artifacts to execution attempts.
This lets future UI, replay, and audit surfaces show outputs per runtime
session.

Artifact registration is part of the execution outcome. Invalid artifact kinds
cause invocation failure. An invocation must not be marked `completed` if
artifact registration fails. `tool_execution_failed` should describe the failure.

## Future Behavior

Future runtime work may add:

- `ToolExecutionAdapter` for executing registered tools
- transition from `running` to `completed` or `failed`
- artifact creation and linkage from tool outputs
- governance warnings or blocks before execution
- risk metadata on tool definitions

## Non-Goals

This ADR does not introduce:

- actual tool execution
- real filesystem writes
- patch application
- shell execution
- filesystem mutation
- ReAct loop
- MCP
- UI
- BEAM, Elixir, Kafka, or Event Fabric work
