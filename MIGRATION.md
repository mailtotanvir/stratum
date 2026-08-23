# Stratum Migration Notes — Execution-First Rebuild (v2)

Date: 2026-08-22
Directive: `STRATUM_EXECUTION_FIRST_REBUILD.md`

The pre-rebuild codebase (~300 backend modules: 100+ models, 150+ services,
70+ routes, projections, decision intelligence, evaluation registries,
operator-console plumbing) evolved top-down around *representations* of
execution before a working execution engine existed. Per the directive, the
runtime was reconstructed around the execution spine and prior code was
classified strictly by its causal connection to real execution.

## Verdict summary

| Verdict | Scope | Where it lives now |
|---|---|---|
| KEEP (principles) | Architecture principles: local-first, event authority, adapter-first provider layer, approval as boundary, rebuildable projections | `stratum/ARCHITECTURE.md` |
| REWRITE | Provider invocation, planning, proposals/approvals, tool execution, events, reconstruction | New `stratum/src/stratum/*` |
| QUARANTINE | Entire old backend application (`backend/app/**`, `backend/tests/**`) + Tauri/React desktop console (`desktop/**`) | Untouched on disk; excluded from runtime path; no imports from new package |
| DELETE (from critical path) | All simulated state producers: mock providers as primary paths, projection builders without runtime producers, dashboard endpoints, decision/evaluation intelligence with no execution producer | Removed by exclusion — nothing in `stratum/` references them |

## What was kept, conceptually

- **OpenAI-compatible transport idea** (`backend/app/providers/httpx_transport.py`,
  `openai_compatible*.py`) — rewritten cleanly as
  `stratum/adapters/openai_compatible.py` using httpx directly, with no SDK
  object model leaking into the core.
- **Event-sourcing posture** — "runtime events are authoritative,
  projections are rebuildable" now has an actual implementation:
  append-only contract (`events.py`), broker publisher/consumer
  (`redpanda.py`), pure replay fold (`replay.py`).
- **Approval-as-boundary** — previously a HITL service over simulated
  proposals; now a structural guard in `engine.py` plus policy objects.

## Why quarantine instead of mass deletion

Physical deletion of ~40k lines in the same change would have made review
impossible and destroyed reference value for selectively re-importing
projections later. The directive allows quarantine for subsystems whose
causal links to real execution could not be established. Consequences:

- The new runtime never imports anything from `backend/app`.
- `desktop/` remains but is not on any acceptance path.
- Old `backend/tests` still pass or fail independently; they assert nothing
  about the v2 runtime.

Recommended follow-up (not done here, deliberately): once the v2 spine has
been stable for some time, delete `backend/` and `desktop/` wholesale and
resurrect only proven-valuable pieces against the new seams.

## Old -> new mapping

| Old subsystem | Disposition | New home |
|---|---|---|
| providers/{transport,httpx_transport,openai_compatible*} | REWRITE | `adapters/openai_compatible.py`, `ai.py` |
| planner/{adapter,mock} | REWRITE | `planning.py` (strict schema validation replaces prose plans) |
| services/proposal_service + hitl_service | REWRITE | `approval.py` + engine guard |
| services/tool_execution_service + tools/* | REWRITE | `tools.py` (workspace containment enforced) |
| models/runtime_event + services/event_service | REWRITE | `events.py`, `publisher.py`, `journal.py`, `redpanda.py` |
| services/runtime_reconstruction_service / reconstruct routes | REWRITE | `replay.py` (pure fold over durable events) |
| db/schema.py (dozens of tables) | QUARANTINE | none — journal NDJSON + broker are the record |
| routes/** (70+ operator-console routers) | QUARANTINE | `api.py` (6 thin routes over the same engine) |
| services/*projection*, *intelligence*, *diagnostics*, *analytics* | QUARANTINE | none yet; rebuildable later FROM the event stream |
| sdk/, query/, skills/ registries | QUARANTINE | none |
| scripts/live_provider_smoke.py | SUPERSEDED | `tests/acceptance/test_real_provider.py` |

## Acceptance evidence produced by this rebuild

1. Vertical integration (scripted provider): real git repo, real file
   mutation, real pytest subprocess, full event chain, journal persistence,
   replay equality — `tests/test_engine_vertical.py`.
2. Real-provider acceptance: live OpenAI-compatible endpoint produces a
   structured plan; approval gate crossed; repository transformed;
   verification passed; replay clean — `tests/acceptance/test_real_provider.py`
   (passes against Groq `openai/gpt-oss-20b`; auto-configures via env).
3. Broker acceptance: publish -> Redpanda -> read -> identical replay —
   `tests/acceptance/test_redpanda.py` (verified live against Redpanda
   v24.2.7 via `docker-compose.redpanda.yml`; compose file at repo root).
4. Full-stack live run: CLI task -> real provider -> approval -> execution
   with events published to Redpanda, replay served from the broker, and
   `stratum consume` rendering the live trace.
5. Persistence (SQLite, v2.1): two-table local store (event index +
   execution projection). Proven live: server killed with a pending
   approval -> restarted -> auto-resumed -> approved over HTTP -> executed;
   duplicate-approve correctly refused by the terminal-state guard. The
   NDJSON journal was superseded by SQLite; FileEventJournal remains only
   as legacy reference code.
4. CLI product surface demonstrated end-to-end: plan display, y/N prompt,
   execution report, `stratum replay`.

## Deliberately NOT done

- No deletion of `backend/` / `desktop/` (see above).
- No FastAPI beyond the thin adapter; no auth/multi-tenancy story.
- No additional topics, partitions, consumers, or projections.
- No UI work of any kind.
