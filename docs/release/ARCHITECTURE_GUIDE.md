# Architecture Guide

## Platform Shape

Stratum is organized around an event-first runtime:

1. Runtime Kernel schedules and coordinates execution.
2. Runtime Event Store records authoritative history.
3. Runtime Sessions bind work to a governed execution context.
4. Workspace and Repository runtimes expose local engineering context.
5. Provider infrastructure isolates model and transport differences.
6. Universal Execution Fabric keeps execution participant abstraction stable.
7. Agent Marketplace and Skills provide extensibility without core lock-in.
8. Evaluation, artifacts, and projections are deterministic derived state.

## Freeze Rules

- No feature additions in RC1.
- No new public surface without corresponding documentation and validation.
- All projections must be reconstructable from the event store and linked artifacts.
- The backend remains the runtime authority; the desktop remains an operator client.

## Diagrams

### Runtime Flow

```mermaid
flowchart LR
  Repo[Repository Runtime] --> WS[Workspace Runtime]
  WS --> Task[Task + Planning]
  Task --> Provider[Provider Infrastructure]
  Provider --> Kernel[Runtime Kernel]
  Kernel --> Store[Runtime Event Store]
  Store --> Timeline[Timeline + Replay]
  Store --> Approvals[Approvals + Governance]
  Store --> Artifacts[Artifacts + Patch Lifecycle]
  Store --> Eval[Evaluation Framework]
  Store --> Summary[Session Summary]
  Summary --> Replay[Replay]
```

### Architecture Boundary

```mermaid
flowchart TB
  Desktop[Desktop Console] <-- localhost/HTTP/SSE --> Backend[FastAPI Backend]
  Backend <-- WSL local filesystem --> Workspace[Workspace / Repository]
  Backend --> Store[Event Store]
  Backend --> Providers[External Providers]
  Backend --> Adapters[Agents / Skills / MCP / A2A Adapters]
```
