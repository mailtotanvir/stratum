"""Structured plans and the planner.

The AI must return a structured plan — explicit steps with a small action
vocabulary — never free-form prose instructions. The planner enforces the
schema; invalid model output is a hard error, not a best-effort guess.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ai import AIAdapter, AIRequest, AIMessage
from .context import RepoContext, render_prompt_context
from .errors import PlanValidationError
from .ids import plan_id

ACTION_TYPES = ("read_file", "write_file", "run_command")
RISK_LEVELS = ("low", "medium", "high")

PLAN_JSON_INSTRUCTIONS = """\
Respond with ONLY a JSON object matching exactly this schema:
{
  "rationale": string,
  "steps": [
    {
      "description": string,
      "action_type": "read_file" | "write_file" | "run_command",
      "path": string | null,
      "content_summary": string | null,
      "content": string | null,
      "command": string | null,
      "risk": "low" | "medium" | "high",
      "requires_approval": boolean
    }
  ]
}

Rules:
- action_type MUST be one of read_file, write_file, run_command.
- For write_file steps: set "path" to the target file relative to the repo
  root and put a concise summary of the intended change in
  "content_summary". If you already know the complete new file content
  (e.g. the current content is in the context), provide it in "content";
  otherwise leave "content" null and the runtime will materialize it from
  the read step at execution time.
- For run_command steps: set "command" to the exact shell command.
- Paths are always relative to the repository root.
- End the plan with a verification command step (e.g. running the tests)
  when one exists.
- Every step that mutates the repository (write_file, run_command) must
  have requires_approval set to true.
"""

SYSTEM_PROMPT = """\
You are Stratum's planner: a careful software engineer that produces \
minimal, safe, verifiable repository transformation plans. You propose; \
a human approves; the runtime executes. Output strict JSON only."""


@dataclass(frozen=True)
class PlanStep:
    index: int
    id: str
    description: str
    action_type: str
    path: str | None = None
    content_summary: str | None = None
    content: str | None = None
    command: str | None = None
    risk: str = "medium"
    requires_approval: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "id": self.id,
            "description": self.description,
            "action_type": self.action_type,
            "path": self.path,
            "content_summary": self.content_summary,
            # Full content is persisted too so a hydrated execution can
            # execute the step verbatim after a restart.
            "content": self.content,
            "command": self.command,
            "risk": self.risk,
            "requires_approval": self.requires_approval,
        }


@dataclass(frozen=True)
class Plan:
    id: str
    task_id: str
    rationale: str
    steps: tuple[PlanStep, ...]
    provider: str = ""
    model: str = ""

    def summary_lines(self) -> list[str]:
        lines = []
        for step in self.steps:
            marker = "*" if step.requires_approval else " "
            detail = step.command or step.path or ""
            lines.append(f"{marker} {step.index}. [{step.action_type}] {step.description}"
                         + (f" ({detail})" if detail else ""))
        return lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "rationale": self.rationale,
            "provider": self.provider,
            "model": self.model,
            "steps": [s.to_dict() for s in self.steps],
        }

    # -- persistence helpers -------------------------------------------------

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str | bytes) -> "Plan":
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        steps = tuple(
            PlanStep(
                index=s["index"],
                id=s["id"],
                description=s.get("description", s.get("action_type", "")),
                action_type=s["action_type"],
                path=s.get("path"),
                content_summary=s.get("content_summary"),
                content=s.get("content"),
                command=s.get("command"),
                risk=s.get("risk", "medium"),
                requires_approval=bool(s.get("requires_approval", True)),
            )
            for s in data.get("steps", [])
        )
        return cls(
            id=data["id"],
            task_id=data["task_id"],
            rationale=data.get("rationale", ""),
            steps=steps,
            provider=data.get("provider", ""),
            model=data.get("model", ""),
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PlanValidationError(message)


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_plan(raw_content: str, *, task_id: str, provider: str = "", model: str = "") -> Plan:
    """Parse and validate model output into a Plan. Raises on any violation."""
    text = raw_content.strip()
    if text.startswith("```"):
        # Tolerate fenced JSON from models that ignore response_format.
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlanValidationError(f"model output is not valid JSON: {exc}") from exc

    _require(isinstance(data, dict), "plan payload must be a JSON object")
    rationale = _clean_str(data.get("rationale"))
    _require(rationale is not None, "plan missing 'rationale'")

    raw_steps = data.get("steps")
    _require(isinstance(raw_steps, list) and len(raw_steps) > 0, "plan must contain steps[]")

    steps: list[PlanStep] = []
    pid = plan_id()
    for i, raw_step in enumerate(raw_steps, start=1):
        _require(isinstance(raw_step, dict), f"step {i} is not an object")
        action_type = _clean_str(raw_step.get("action_type"))
        _require(
            action_type in ACTION_TYPES,
            f"step {i}: unknown action_type {action_type!r} (allowed: {ACTION_TYPES})",
        )
        assert action_type is not None
        description = _clean_str(raw_step.get("description")) or action_type
        risk = (_clean_str(raw_step.get("risk")) or "medium").lower()
        _require(risk in RISK_LEVELS, f"step {i}: invalid risk {risk!r}")
        path = _clean_str(raw_step.get("path"))
        command = _clean_str(raw_step.get("command"))

        if action_type == "write_file":
            _require(path is not None, f"step {i}: write_file requires 'path'")
            _require(
                not path.startswith("/") and ".." not in Path(path).parts,
                f"step {i}: write_file path must be relative and inside the repo",
            )
        if action_type == "run_command":
            _require(command is not None, f"step {i}: run_command requires 'command'")

        mutates = action_type in ("write_file", "run_command")
        requires_approval = bool(raw_step.get("requires_approval", True)) or mutates

        content = raw_step.get("content")
        _require(
            content is None or isinstance(content, str),
            f"step {i}: 'content' must be a string when provided",
        )

        steps.append(
            PlanStep(
                index=len(steps) + 1,
                id=f"{pid}-s{len(steps) + 1}",
                description=description,
                action_type=action_type,
                path=path,
                content_summary=_clean_str(raw_step.get("content_summary")),
                content=content,
                command=command,
                risk=risk,
                requires_approval=requires_approval,
            )
        )

    return Plan(
        id=pid,
        task_id=task_id,
        rationale=rationale,
        steps=tuple(steps),
        provider=provider,
        model=model,
    )


class Planner:
    """Builds the structured planning prompt from bounded context."""

    def __init__(self, adapter: AIAdapter | None = None, *, model: str) -> None:
        self._adapter = adapter
        self._model = model

    def build_request(self, ctx: RepoContext) -> AIRequest:
        prompt_context = render_prompt_context(ctx)
        user_message = (
            f"# Task\n{ctx.task_description}\n\n"
            f"# Repository context\n{prompt_context}\n\n"
            f"# Your output format\n{PLAN_JSON_INSTRUCTIONS}"
        )
        return AIRequest(
            model=self._model,
            messages=(
                AIMessage(role="system", content=SYSTEM_PROMPT),
                AIMessage(role="user", content=user_message),
            ),
            temperature=0.0,
            response_json=True,
            metadata={"purpose": "planning"},
        )

