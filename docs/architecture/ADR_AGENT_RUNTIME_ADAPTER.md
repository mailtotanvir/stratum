# ADR: Agent Runtime Adapter Boundary

## Status

Accepted for Stratum v1.

## Context

Stratum needs an agent execution loop that can run productively on a local
workstation in v1 while leaving room for a future runtime with stronger
distribution and fault-tolerance characteristics. The runtime choice should not
be allowed to leak into task handling, governance, event delivery, proposal
creation, or artifact creation.

## Decision

Stratum v1 will use `PythonAsyncRuntime` as the agent runtime backend.

The agent loop must be designed behind an Agent Runtime Adapter boundary. The
runtime backend is replaceable, and application code should depend on the
adapter contract rather than on `PythonAsyncRuntime` details.

## Stable Contract

Any Agent Runtime Adapter must:

- accept tasks through a stable task submission interface
- emit `RuntimeEvents` through the stable runtime event interface
- obey `GovernanceService` decisions before continuing governed work
- support a future interrupt/stop control path
- produce proposals and artifacts through stable proposal and artifact
  interfaces

## Future Option

`BeamOtpRuntime` is a future backend option. It may provide a path toward
enterprise-scale supervision, distribution, and fault isolation while preserving
the same external adapter contract.

## Non-Goal

Stratum v1 will not include an Elixir/BEAM implementation.

## Rationale

`PythonAsyncRuntime` preserves local workstation velocity for v1: it keeps the
runtime close to the current backend stack, simplifies development and testing,
and avoids prematurely introducing cross-language operational complexity.

Keeping the Agent Runtime Adapter boundary explicit preserves an enterprise-scale
path. If Stratum later needs BEAM-style supervision or distributed execution, the
backend can be replaced without rewriting the task API, governance flow, event
stream, proposal path, or artifact interfaces.

## Appendix: Everything as a Marketplace Adapter

Stratum should treat external agent systems as replaceable marketplace
adapters, not as part of the runtime core.

This means:

- hosted agents, multi-agent systems, research agents, coding agents, marketing
  agents, MCP servers, and A2A-compatible agents all integrate through
  adapters
- Stratum keeps governance, observation, approvals, audit trail, artifacts, and
  event history under its own control
- agent providers and ecosystems remain swappable without changing the
  substrate
- future MCP and A2A protocol support should be implemented at the adapter
  layer, not by coupling those protocols into runtime internals

The architectural intent is to preserve a stable Stratum core while allowing
many external agent products and ecosystems to plug in, evolve, or be replaced
independently.
