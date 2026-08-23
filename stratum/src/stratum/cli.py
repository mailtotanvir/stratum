"""Stratum CLI — the first product surface.

The CLI exercises the exact same runtime as the FastAPI adapter. No HTTP,
no UI, no framework required.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from .adapters.openai_compatible import OpenAICompatibleAdapter
from .approval import InteractiveApprovalPolicy
from .engine import ExecutionStatus, StratumRuntime
from .errors import StratumError
from .events import DEFAULT_TOPIC
from .planning import Planner
from .publisher import CompositeEventPublisher
from .replay import fold, format_trace_line, render_narrative


def _env(name: str, *fallbacks: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    for candidate in fallbacks:
        value = os.environ.get(candidate)
        if value:
            return value
    return None


def _default_data_dir() -> Path:
    override = os.environ.get("STRATUM_DATA_DIR")
    return Path(override) if override else Path.cwd() / ".stratum-data"


def _resolve_broker(args: argparse.Namespace) -> list[str] | None:
    brokers = getattr(args, "brokers", None) or _env("STRATUM_KAFKA_BROKERS")
    if not brokers:
        return None
    return [b.strip() for b in brokers.split(",") if b.strip()]


def _build_adapter(args: argparse.Namespace):
    from .config import resolve_provider

    config = resolve_provider(
        base_url=getattr(args, "provider_base_url", None),
        model=args.model,
    )
    if config is None:
        raise StratumError(
            "no provider configured: set STRATUM_PROVIDER_API_KEY/"
            "STRATUM_PROVIDER_BASE_URL (or OPENAI_API_KEY / GROQ_API_KEY)"
        )
    if not config.model:
        raise StratumError("no model: pass --model or set STRATUM_MODEL")
    return OpenAICompatibleAdapter(
        base_url=config.base_url, api_key=config.api_key), config.model


def _require_model(args: argparse.Namespace) -> str:
    from .config import resolve_provider

    config = resolve_provider(model=args.model)
    if config is None or not config.model:
        raise StratumError("no model: pass --model or set STRATUM_MODEL")
    return config.model


# ---------------------------------------------------------------------------
# stratum run
# ---------------------------------------------------------------------------


async def cmd_run(args: argparse.Namespace) -> int:
    adapter, model = _build_adapter(args)

    data_dir = Path(args.data_dir) if args.data_dir else _default_data_dir()
    store = _open_store(data_dir)

    publishers = []
    broker = _resolve_broker(args)
    if broker:
        from .redpanda import RedpandaEventPublisher

        publishers.append(RedpandaEventPublisher(brokers=broker, topic=args.topic))
    publisher = (
        CompositeEventPublisher(*publishers) if publishers else _StoreOnlyPublisher(store)
    )

    runtime = StratumRuntime(
        adapter=adapter,
        model=model,
        publisher=publisher,
        approval_policy=InteractiveApprovalPolicy(),
        planner=Planner(model=model),
        store=store,
    )

    print("Repository validated.")
    print("\nPlanning...\n")

    snapshot = await runtime.start_planning(
        repo_path=Path(args.repo).expanduser().resolve(),
        task_description=args.task,
        selected_files=list(args.file) if args.file else None,
        markdown_context=_read_context_file(args.context),
    )

    if snapshot.status == ExecutionStatus.FAILED:
        print(f"Task failed before approval: {snapshot.error}")
        return 1

    assert snapshot.plan is not None

    # The approval boundary is consulted here, between planning and any side
    # effect. decide_and_execute is structurally unreachable otherwise.
    record = InteractiveApprovalPolicy().decide(
        snapshot.execution_id, snapshot.plan)

    result = await runtime.decide_and_execute(snapshot.execution_id, record)

    if record.decision == "granted":
        print("\nExecuting...\n")
        for observation in result.observations:
            icon = "+" if observation.get("ok") else "x"
            print(f"  [{icon}] {observation.get('summary', '')}")

    print(f"\nTask {result.status.value}.")
    if result.error:
        print(f"Error: {result.error}")
    print(f"Execution ID: {result.execution_id}")
    print(f"History DB:   {store.path}")
    print(f"\nReplay:\n  stratum replay {result.execution_id}"
          + (f" --brokers {','.join(broker)}" if broker else ""))
    return 0 if result.status in (ExecutionStatus.COMPLETED,) else 2


class _StoreOnlyPublisher:
    """Publisher that only writes the local store (no broker configured)."""

    def __init__(self, store) -> None:
        import asyncio

        from .store import AsyncSqliteStore

        # Accept raw or async stores; writes must be offloaded either way.
        self._append = (
            store.append if isinstance(store, AsyncSqliteStore)
            else (lambda event: asyncio.to_thread(store.append, event))
        )

    async def publish(self, event) -> None:
        await self._append(event)

    async def close(self) -> None:
        return None


def _open_store(data_dir: Path):
    from .store import SqliteEventStore

    return SqliteEventStore(data_dir / "stratum.db")


def _read_context_file(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_file():
        raise StratumError(f"context file not found: {path}")
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# stratum replay
# ---------------------------------------------------------------------------


def _read_events_for_replay(args: argparse.Namespace, execution_id: str):
    broker = _resolve_broker(args)
    if broker:
        from .redpanda import BrokerUnavailable, RedpandaEventReader

        reader = RedpandaEventReader(brokers=broker, topic=args.topic)
        try:
            events = reader.read_execution(execution_id)
        except BrokerUnavailable as exc:
            raise StratumError(f"broker unavailable: {exc}") from exc
        if events:
            return events

    data_dir = Path(args.data_dir) if args.data_dir else _default_data_dir()
    store_events = _open_store(data_dir).read_execution(execution_id)
    if store_events and broker:
        print("(note: execution not found on broker; using local database)",
              file=sys.stderr)
    return store_events


def cmd_replay(args: argparse.Namespace) -> int:
    events = _read_events_for_replay(args, args.execution_id)
    if not events:
        print(f"No recorded events found for {args.execution_id}", file=sys.stderr)
        return 1
    replayed = fold(events)
    print(render_narrative(replayed))
    print(f"\n({len(events)} events replayed; no AI calls, no side effects)")
    return 0 if replayed.status == "COMPLETED" else 2


# ---------------------------------------------------------------------------
# stratum consume
# ---------------------------------------------------------------------------


async def cmd_consume(args: argparse.Namespace) -> int:
    broker = _resolve_broker(args)
    if not broker:
        raise StratumError(
            "consume requires a broker: pass --brokers or set STRATUM_KAFKA_BROKERS"
        )
    from .redpanda import RedpandaEventReader

    reader = RedpandaEventReader(brokers=broker, topic=args.topic)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def produce_lines():
        try:
            for event in reader.iter_events(follow=args.follow):
                loop.call_soon_threadsafe(queue.put_nowait, format_trace_line(event))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    import threading

    thread = threading.Thread(target=produce_lines, daemon=True)
    thread.start()

    while True:
        line = await queue.get()
        if line is None:
            break
        print(line)
    return 0


# ---------------------------------------------------------------------------
# stratum doctor
# ---------------------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace) -> int:
    from .config import resolve_provider

    checks: list[tuple[str, bool, str]] = []

    config = resolve_provider()
    checks.append((
        "provider configured (paired base URL + API key)",
        bool(config),
        config.base_url if config else "-",
    ))
    checks.append((
        "model configured",
        bool(config and config.model),
        (config.model if config else "") or "-",
    ))

    broker = _resolve_broker(args)
    checks.append(("event broker configured", bool(broker), ",".join(broker or []) or "-"))
    if broker:
        try:
            from kafka import KafkaConsumer  # noqa: PLC0415

            consumer = KafkaConsumer(bootstrap_servers=broker)
            consumer.topics()
            consumer.close()
            reachable = True
            detail = "reachable"
        except Exception as exc:  # noqa: BLE001
            reachable = False
            detail = f"unreachable: {exc}"
        checks.append(("event broker reachable", reachable, detail))

    git_ok = True
    try:
        import subprocess

        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except Exception:  # noqa: BLE001
        git_ok = False
    checks.append(("git available", git_ok, ""))

    failed = False
    for name, ok, detail in checks:
        print(f"[{'ok' if ok else 'MISSING'}] {name}" + (f": {detail}" if detail else ""))
        failed = failed or not ok
    return 1 if failed else 0


# ---------------------------------------------------------------------------
# stratum serve (browser UI)
# ---------------------------------------------------------------------------


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .config import resolve_provider
    from .webui import create_web_app
    from .api import RuntimeHolder

    data_dir = Path(args.data_dir) if args.data_dir else _default_data_dir()
    store = _open_store(data_dir)

    publishers = []
    broker = _resolve_broker(args)
    if broker:
        from .redpanda import RedpandaEventPublisher

        publishers.append(RedpandaEventPublisher(brokers=broker, topic=args.topic))

    config = resolve_provider(model=args.model)
    adapter, model = _build_adapter(args)

    from .engine import StratumRuntime
    from .planning import Planner
    from .publisher import CompositeEventPublisher

    runtime = StratumRuntime(
        adapter=adapter,
        model=model,
        publisher=(
            CompositeEventPublisher(*publishers)
            if publishers else _StoreOnlyPublisher(store)
        ),
        approval_policy=_WebApprovalPolicy(),
        planner=Planner(model=model),
        store=store,
    )

    resumed = asyncio.run(runtime.resume_pending())
    if resumed:
        print(f"Resumed {len(resumed)} pending execution(s) awaiting approval:")
        for snap in resumed:
            print(f"  {snap.execution_id}  {snap.task_description[:60]}")

    holder = RuntimeHolder(
        runtime=runtime,
        read_events=store.read_execution,
        list_executions=_store_list_executions(store),
    )
    app = create_web_app(holder, meta={
        "broker": bool(broker),
        "provider": config.base_url if config else "",
        "model": model,
    })

    print(f"Stratum console:  http://127.0.0.1:{args.port}")
    print(f"Provider:         {config.base_url if config else '-'} ({model})")
    print(f"Broker:           {','.join(broker) if broker else 'journal-only'}")
    print(f"History DB:       {store.path}")
    print("Press Ctrl+C to stop.")
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    finally:
        store.close()
    return 0


def _store_list_executions(store):
    def _list(limit: int = 200):
        return [
            {
                "execution_id": r.execution_id,
                "task_id": r.task_id,
                "description": r.task_description,
                "repo_path": r.repo_path,
                "status": r.status,
                "approval": (
                    None if r.decider is None
                    else ("rejected" if r.status == "REJECTED" else "granted")
                ),
                "decider": r.decider,
                "error": r.error,
                "started_at": r.created_at,
                "ended_at": r.updated_at,
                "event_count": r.last_event_sequence,
            }
            for r in store.list_executions(limit)
        ]
    return _list


class _WebApprovalPolicy:
    """Placeholder policy for the web server process.

    Approval decisions arrive over HTTP as explicit ApprovalRecords; the
    engine consults the policy only when no record is supplied. If a client
    somehow triggers decision without a record, we refuse rather than guess.
    """

    def decide(self, execution_id, plan):
        from .errors import StratumError

        raise StratumError(
            "web transport requires an explicit approve/reject decision"
        )


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stratum",
        description="Stratum - local-first AI execution runtime",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common_broker = argparse.ArgumentParser(add_help=False)
    common_broker.add_argument(
        "--brokers",
        help="comma-separated Kafka/Redpanda bootstrap servers "
             "(default: $STRATUM_KAFKA_BROKERS; omit for journal-only mode)",
    )
    common_broker.add_argument("--topic", default=DEFAULT_TOPIC)

    p_run = sub.add_parser(
        "run", parents=[common_broker],
        help="plan a repository transformation and execute it after approval",
    )
    p_run.add_argument("--repo", required=True, help="path to the target repository")
    p_run.add_argument("--task", required=True, help="engineering task description")
    p_run.add_argument("--model", help="model id (or set STRATUM_MODEL)")
    p_run.add_argument("--file", action="append", help="repo-relative file to include in context (repeatable)")
    p_run.add_argument("--context", help="markdown file with extra operator context")
    p_run.add_argument("--data-dir", help="directory for the local event journal")
    p_run.set_defaults(func=lambda a: asyncio.run(cmd_run(a)))

    p_replay = sub.add_parser(
        "replay", parents=[common_broker],
        help="reconstruct an execution from its event history (no AI, no effects)",
    )
    p_replay.add_argument("execution_id")
    p_replay.add_argument("--data-dir", help="directory of the local event journal")
    p_replay.set_defaults(func=cmd_replay)

    p_consume = sub.add_parser(
        "consume", parents=[common_broker],
        help="print a live human-readable trace from the event stream",
    )
    p_consume.add_argument("--follow", action="store_true", help="keep streaming new events")
    p_consume.set_defaults(func=lambda a: asyncio.run(cmd_consume(a)))

    p_doctor = sub.add_parser("doctor", parents=[common_broker], help="check local configuration")
    p_doctor.set_defaults(func=cmd_doctor)

    p_serve = sub.add_parser(
        "serve", parents=[common_broker],
        help="run the browser console (FastAPI + static UI)",
    )
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--model", help="model id (or set STRATUM_MODEL)")
    p_serve.add_argument("--data-dir", help="directory for the local event journal")
    p_serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except StratumError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
