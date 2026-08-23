"""Browser UI for UAT — served by the FastAPI adapter.

The UI is just another client of the runtime engine: it submits tasks,
renders the real plan, records the human approval decision via the same
API the CLI uses, streams recorded events, and replays executions from
the journal/broker. It holds no state of its own.
"""

from pathlib import Path

from .api import RuntimeHolder, create_app

WEB_DIR = Path(__file__).parent / "web"


def create_web_app(holder: RuntimeHolder, *, meta: dict | None = None):
    app = create_app(holder)

    from fastapi.staticfiles import StaticFiles

    meta = meta or {}

    @app.get("/executions")
    async def list_executions() -> list[dict]:
        if holder.list_executions is None:
            return []
        return holder.list_executions()

    @app.get("/healthz")
    async def healthz() -> dict:
        return {
            "ok": True,
            "broker": bool(meta.get("broker")),
            "provider": meta.get("provider", ""),
            "model": meta.get("model", ""),
        }

    # Static UI last, so API routes win.
    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="ui")

    return app


def journal_list_executions(journal):
    """Builds a history-listing callable over the event journal."""

    from .events import sort_events
    from .replay import fold

    def _list() -> list[dict]:
        out: dict[str, dict] = {}
        for execution_id, events in _group_by_execution(journal.read_all()):
            ordered = sort_events(events)
            replayed = fold(ordered)
            out[execution_id] = {
                "execution_id": execution_id,
                "task_id": replayed.task_id,
                "description": replayed.description,
                "repo_path": replayed.repo_path,
                "status": replayed.status,
                "approval": replayed.approval,
                "error": replayed.error,
                "started_at": replayed.first_timestamp,
                "ended_at": replayed.last_timestamp,
                "event_count": len(ordered),
            }
        rows = sorted(out.values(), key=lambda r: r["started_at"] or "")
        return list(reversed(rows))

    return _list


def _group_by_execution(events):
    grouped: dict[str, list] = {}
    for event in events:
        grouped.setdefault(event.execution_id, []).append(event)
    return grouped.items()
