"""Replay — reconstruct executions from their event history.

Replay NEVER invokes the AI and NEVER repeats side effects. It reads the
recorded event stream, folds it into state, and reproduces the execution
narrative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .events import (
    AI_REQUESTED,
    AI_RESPONDED,
    APPROVAL_GRANTED,
    APPROVAL_REJECTED,
    ARTIFACT_CREATED,
    EXECUTION_STARTED,
    OBSERVATION_RECORDED,
    PLAN_GENERATED,
    TASK_CANCELLED,
    TASK_COMPLETED,
    TASK_CREATED,
    TASK_FAILED,
    TOOL_COMPLETED,
    TOOL_FAILED,
    TOOL_STARTED,
    RuntimeEvent,
    sort_events,
)


@dataclass
class ReplayedExecution:
    execution_id: str
    task_id: str = ""
    repo_path: str = ""
    description: str = ""
    status: str = "UNKNOWN"
    rationale: str = ""
    plan_steps: list[dict[str, Any]] = field(default_factory=list)
    approval: str | None = None
    decider: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    events: list[RuntimeEvent] = field(default_factory=list)


def fold(events: list[RuntimeEvent]) -> ReplayedExecution:
    """Pure fold of one execution's events into reconstructed state."""
    ordered = sort_events(events)
    if not ordered:
        raise ValueError("no events to replay")

    out = ReplayedExecution(execution_id=ordered[0].execution_id)

    for event in ordered:
        out.task_id = event.task_id or out.task_id
        if out.first_timestamp is None:
            out.first_timestamp = event.timestamp
        out.last_timestamp = event.timestamp
        p = event.payload

        if event.event_type == TASK_CREATED:
            out.description = p.get("description", "")
            out.repo_path = p.get("repo_path", "")
        elif event.event_type == PLAN_GENERATED:
            plan = p.get("plan") or {}
            out.rationale = plan.get("rationale", "")
            out.plan_steps = [
                {
                    "index": s.get("index"),
                    "action_type": s.get("action_type"),
                    "description": s.get("description"),
                    "path": s.get("path"),
                    "command": s.get("command"),
                }
                for s in plan.get("steps", [])
            ]
        elif event.event_type == APPROVAL_GRANTED:
            out.approval = "granted"
            out.decider = p.get("decider")
        elif event.event_type == APPROVAL_REJECTED:
            out.approval = "rejected"
            out.decider = p.get("decider")
            out.status = "REJECTED"
        elif event.event_type == EXECUTION_STARTED:
            if out.status in ("UNKNOWN",):
                out.status = "EXECUTING"
        elif event.event_type == TOOL_STARTED:
            out.tool_calls.append({
                "index": p.get("index"),
                "action_type": p.get("action_type"),
                "state": "started",
                "timestamp": event.timestamp,
            })
        elif event.event_type == TOOL_COMPLETED:
            for call in reversed(out.tool_calls):
                if call["index"] == p.get("index") and call["state"] == "started":
                    call["state"] = "completed"
                    call["summary"] = p.get("summary")
                    break
        elif event.event_type == TOOL_FAILED:
            for call in reversed(out.tool_calls):
                if call["index"] == p.get("index") and call["state"] == "started":
                    call["state"] = "failed"
                    call["error"] = p.get("error")
                    break
        elif event.event_type == ARTIFACT_CREATED:
            out.artifacts.append({
                "path": p.get("path"),
                "bytes": p.get("bytes"),
                "diff": p.get("diff", ""),
            })
        elif event.event_type == OBSERVATION_RECORDED:
            if p.get("ok") is False or "exit_code" in p:
                out.observations.append({
                    "index": p.get("index"),
                    "ok": p.get("ok"),
                    "summary": p.get("summary"),
                })
        elif event.event_type == TASK_COMPLETED:
            out.status = "COMPLETED"
        elif event.event_type == TASK_FAILED:
            out.status = "FAILED"
            out.error = p.get("error")
        elif event.event_type == TASK_CANCELLED:
            out.status = "CANCELLED"

    return out


def render_narrative(replay: ReplayedExecution) -> str:
    """Human-readable execution trace, like a receipt of what happened."""
    lines: list[str] = []
    stamp = lambda ts: (ts or "")[11:19]  # noqa: E731

    lines.append(f"Execution {replay.execution_id}")
    lines.append(f"  Task:     {replay.description}")
    lines.append(f"  Repo:     {replay.repo_path}")
    if replay.plan_steps:
        lines.append(f"  Plan ({len(replay.plan_steps)} steps): {replay.rationale[:120]}")
        for s in replay.plan_steps:
            detail = s.get("command") or s.get("path") or ""
            lines.append(
                f"    {s['index']}. [{s['action_type']}] {s['description']}"
                + (f" ({detail})" if detail else "")
            )
    if replay.approval:
        lines.append(
            f"  Approval: {replay.approval}"
            + (f" by {replay.decider}" if replay.decider else "")
        )

    for call in replay.tool_calls:
        icon = {"completed": "+", "failed": "x", "started": ">"}.get(call["state"], "?")
        line = f"  [{icon}] {stamp(call['timestamp'])} {call['action_type']}"
        if call["state"] == "failed":
            line += f" FAILED: {call.get('error')}"
        elif call["state"] == "completed":
            line += f" - {call.get('summary')}"
        lines.append(line)

    for artifact in replay.artifacts:
        lines.append(f"  artifact: {artifact['path']} ({artifact['bytes']} bytes)")

    lines.append(f"  Status:   {replay.status}"
                 + (f" - {replay.error}" if replay.error else ""))
    return "\n".join(lines)


def format_trace_line(event: RuntimeEvent) -> str:
    """One human-readable line per event, for the live consumer."""
    time_part = event.timestamp[11:19]
    p = event.payload
    detail = ""
    if event.event_type in (TOOL_STARTED, TOOL_COMPLETED, TOOL_FAILED):
        label = p.get("action_type") or p.get("command") or ""
        extra = p.get("summary") or p.get("error") or p.get("path") or ""
        detail = f" {label}".rstrip() + (f" - {extra}" if extra else "")
    elif event.event_type == AI_REQUESTED:
        detail = f" {p.get('purpose')} model={p.get('model')}"
    elif event.event_type == AI_RESPONDED:
        usage = p.get("usage") or {}
        detail = (
            f" {p.get('purpose')} tokens={usage.get('total_tokens', '?')}"
            f" latency={p.get('latency_ms')}ms"
        )
    elif event.event_type == PLAN_GENERATED:
        plan = p.get("plan") or {}
        detail = f" {len(plan.get('steps', []))} steps"
    elif event.event_type in (APPROVAL_GRANTED, APPROVAL_REJECTED):
        detail = f" by {p.get('decider')}"
    elif event.event_type == TASK_COMPLETED:
        detail = f" steps_ok={p.get('steps_ok')}/{p.get('steps_total')}"
    elif event.event_type == ARTIFACT_CREATED:
        detail = f" {p.get('path')} ({p.get('bytes')} bytes)"
    return f"{time_part} {event.event_type}{detail}"
