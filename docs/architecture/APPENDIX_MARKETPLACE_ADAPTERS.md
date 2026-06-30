# Appendix: Marketplace Adapters

Stratum treats external agent systems as marketplace adapters that sit outside
the core runtime. The core keeps control of governance, approvals, event
history, and artifact storage.

This appendix is intentionally ecosystem-neutral. It applies to:

- hosted agents
- MCP-backed agents
- A2A-compatible agents
- coding agents
- research agents
- multi-agent systems

Adapter contracts should stay focused on capability disclosure, invocation, and
event normalization. Vendor-specific protocols, transport details, and runtime
implementation choices belong behind the adapter boundary.

The backend foundation added in this slice introduces:

- `AgentCapabilityManifest` for capability discovery
- `AgentInvocation` and `AgentInvocationResult` for request/result contracts
- `AgentAdapterRegistryService` for adapter lookup and registration
- `AgentEventBridgeService` for normalizing external agent events into Stratum
  runtime event shapes

## Adapter Lifecycle

The marketplace lifecycle is intentionally deterministic and local:

1. An adapter advertises a manifest.
2. The registry stores the adapter and exposes catalog and diagnostics reads.
3. The invocation service validates the adapter and capability.
4. The runtime seam creates a durable invocation record.
5. The adapter emits normalized lifecycle events and declared artifacts.
6. Stratum records the lifecycle, approvals, and artifacts without delegating
   authority over them to the adapter.

Mock and contract-harness adapters are expected to return deterministic output
for the same invocation input. That keeps the catalog and UI stable while the
real protocol integrations remain out of tree.

## Mock Adapter Demo Flow

The built-in mock external adapter exists only to demonstrate the contract end
to end without network traffic or workspace writes:

- it advertises a hosted transport and demo-only metadata
- the adapter registry exposes it alongside built-in local examples
- the contract harness validates its manifest, invocation result, event
  normalization, artifact declarations, and cancellation behavior
- the desktop marketplace can launch a mock invocation and inspect the emitted
  lifecycle history

The demo adapter may declare artifacts, but those declarations are still
contract-level records. They are not direct filesystem writes.

## Contract Harness Requirements

Future adapter implementations should pass the contract harness before they are
considered integration-ready. A compliant adapter must:

- declare a non-empty manifest with supported capabilities
- return deterministic terminal invocation results
- emit at least one normalized event
- declare artifacts without writing directly to the workspace
- support cancellation explicitly, or raise `NotImplementedError` if
  cancellation is not supported

The harness is a contract gate, not an execution engine. It is meant to catch
adapter drift early, not to simulate real provider execution.

## Integration Guidance

Future MCP, A2A, or vendor adapters should integrate by implementing the
adapter contract and registering through the marketplace boundary. They should
not be wired directly into runtime internals or provider execution semantics.

The runtime core must remain responsible for:

- approval gating
- audit and event-store persistence
- artifact registration and linkage
- cancellation and stop semantics
- policy enforcement
- session reconstruction

External agents must not bypass those surfaces to:

- write directly to workspace files
- emit authoritative runtime events without normalization
- skip approvals or governance checks
- mutate event-store state directly
- short-circuit cancellation or artifact registration

No runtime-loop integration is performed yet. This keeps the adapter seam
available without changing execution, approval, or event-store behavior.
