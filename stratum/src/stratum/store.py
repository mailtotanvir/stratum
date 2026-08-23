"""SQLite persistence — local event index + execution state projection.

Role of this database (deliberately narrow):

1. A queryable LOCAL INDEX of the authoritative event stream. When a broker
   is configured, Redpanda remains the source of truth; this is cache.
   Without a broker it is the persistence boundary of last resort.
2. The EXECUTION STATE PROJECTION that lets the engine (and therefore the
   CLI and web console) survive restarts: a pending APPROVAL_REQUIRED
   execution can be hydrated from here and approved later.

It is NOT a second source of truth: every row here is derivable from
events. Two tables only. WAL journal mode; schema version via user_version.

sqlite3 is used directly — no ORM, no new dependencies.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .events import RuntimeEvent
from .planning import Plan

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ExecutionRecord:
    execution_id: str
    task_id: str
    repo_path: str
    task_description: str
    status: str
    plan: Plan | None
    error: str | None = None
    decider: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    last_event_sequence: int = 0
    correlation_id: str | None = None


class SqliteEventStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.path), check_same_thread=False, timeout=30.0
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"database {self.path} has newer schema v{version} "
                f"(this build understands v{SCHEMA_VERSION})"
            )
        if version == SCHEMA_VERSION and self._table_exists("events"):
            return
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id      TEXT PRIMARY KEY,
                execution_id  TEXT NOT NULL,
                sequence      INTEGER NOT NULL,
                event_type    TEXT NOT NULL,
                event_version INTEGER NOT NULL,
                timestamp     TEXT NOT NULL,
                producer      TEXT,
                payload_json  TEXT NOT NULL,
                correlation_id TEXT,
                causation_id  TEXT,
                recorded_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS ix_events_exec
                ON events (execution_id, sequence);

            CREATE TABLE IF NOT EXISTS executions (
                execution_id       TEXT PRIMARY KEY,
                task_id            TEXT NOT NULL,
                repo_path          TEXT NOT NULL,
                task_description   TEXT NOT NULL,
                status             TEXT NOT NULL,
                plan_json          TEXT,
                error              TEXT,
                decider            TEXT,
                created_at         TEXT NOT NULL,
                updated_at         TEXT NOT NULL,
                last_event_sequence INTEGER NOT NULL DEFAULT 0,
                correlation_id     TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_executions_status
                ON executions (status);
            """
        )
        self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self._conn.commit()

    def _table_exists(self, name: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        return row is not None

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Event index (write side) — idempotent by event_id
    # ------------------------------------------------------------------

    def append(self, event: RuntimeEvent) -> None:
        with self._conn:
            self._append_conn(event)

    def _append_conn(self, event: RuntimeEvent) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO events (
                event_id, execution_id, sequence, event_type, event_version,
                timestamp, producer, payload_json,
                correlation_id, causation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.execution_id,
                event.sequence,
                event.event_type,
                event.event_version,
                event.timestamp,
                event.producer,
                json.dumps(event.payload, separators=(",", ":")),
                event.correlation_id,
                event.causation_id,
            ),
        )

    # ------------------------------------------------------------------
    # Event index (read side)
    # ------------------------------------------------------------------

    def read_all(self) -> list[RuntimeEvent]:
        rows = self._conn.execute(
            "SELECT * FROM events ORDER BY execution_id, sequence"
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def read_execution(self, execution_id: str) -> list[RuntimeEvent]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE execution_id=? ORDER BY sequence",
            (execution_id,),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> RuntimeEvent:
        return RuntimeEvent(
            event_id=row["event_id"],
            event_type=row["event_type"],
            event_version=row["event_version"],
            task_id="",  # not denormalized; recoverable via executions table
            execution_id=row["execution_id"],
            timestamp=row["timestamp"],
            sequence=row["sequence"],
            producer=row["producer"] or "stratum-runtime",
            payload=json.loads(row["payload_json"]),
            correlation_id=row["correlation_id"],
            causation_id=row["causation_id"],
        )

    # ------------------------------------------------------------------
    # Execution state projection
    # ------------------------------------------------------------------

    def upsert_execution(
        self,
        *,
        execution_id: str,
        task_id: str,
        repo_path: str,
        task_description: str,
        status: str,
        created_at: str,
        plan: Plan | None = None,
        error: str | None = None,
        decider: str | None = None,
        last_event_sequence: int = 0,
        correlation_id: str | None = None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO executions (
                    execution_id, task_id, repo_path, task_description,
                    status, plan_json, error, decider,
                    created_at, updated_at,
                    last_event_sequence, correlation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)
                ON CONFLICT(execution_id) DO UPDATE SET
                    status=excluded.status,
                    plan_json=COALESCE(excluded.plan_json, executions.plan_json),
                    error=excluded.error,
                    decider=COALESCE(excluded.decider, executions.decider),
                    updated_at=datetime('now'),
                    last_event_sequence=MAX(
                        executions.last_event_sequence,
                        excluded.last_event_sequence),
                    correlation_id=COALESCE(
                        excluded.correlation_id, executions.correlation_id)
                """,
                (
                    execution_id,
                    task_id,
                    repo_path,
                    task_description,
                    status,
                    plan.to_json() if plan else None,
                    error,
                    decider,
                    created_at,
                    last_event_sequence,
                    correlation_id,
                ),
            )
        # Keep the projection honest: reflect indexed-event watermark too.
        with self._conn:
            self._bump_sequence_from_events(execution_id)

    def _bump_sequence_from_events(self, execution_id: str) -> None:
        row = self._conn.execute(
            "SELECT MAX(sequence) AS s, MIN(correlation_id) AS c "
            "FROM events WHERE execution_id=?",
            (execution_id,),
        ).fetchone()
        if row and row["s"]:
            self._conn.execute(
                """
                UPDATE executions
                SET last_event_sequence = MAX(last_event_sequence, ?),
                    correlation_id = COALESCE(correlation_id, ?)
                WHERE execution_id = ?
                """,
                (row["s"], row["c"], execution_id),
            )

    def get_execution(self, execution_id: str) -> ExecutionRecord | None:
        row = self._conn.execute(
            "SELECT * FROM executions WHERE execution_id=?", (execution_id,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def list_executions(self, limit: int = 200) -> list[ExecutionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM executions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def pending_executions(self) -> list[ExecutionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM executions WHERE status='APPROVAL_REQUIRED' "
            "ORDER BY created_at"
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ExecutionRecord:
        plan = Plan.from_json(row["plan_json"]) if row["plan_json"] else None
        return ExecutionRecord(
            execution_id=row["execution_id"],
            task_id=row["task_id"],
            repo_path=row["repo_path"],
            task_description=row["task_description"],
            status=row["status"],
            plan=plan,
            error=row["error"],
            decider=row["decider"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_event_sequence=row["last_event_sequence"],
            correlation_id=row["correlation_id"],
        )


# ----------------------------------------------------------------------
# Async bridge — engine and API run on an event loop; sqlite is sync.
# ----------------------------------------------------------------------


class AsyncSqliteStore:
    """Thin async facade over SqliteEventStore (thread offloading)."""

    def __init__(self, store: SqliteEventStore) -> None:
        self.store = store

    async def append(self, event: RuntimeEvent) -> None:
        await asyncio.to_thread(self.store.append, event)

    async def upsert_execution(self, **kwargs: Any) -> None:
        await asyncio.to_thread(self.store.upsert_execution, **kwargs)

    # Reads are also offloaded for API endpoints.
    async def read_execution(self, execution_id: str) -> list[RuntimeEvent]:
        return await asyncio.to_thread(self.store.read_execution, execution_id)

    async def read_all(self) -> list[RuntimeEvent]:
        return await asyncio.to_thread(self.store.read_all)
