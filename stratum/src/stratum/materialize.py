"""Grounded write materialization.

When a plan's write_file step carries intent (content_summary) but not
concrete bytes, the runtime performs one additional real provider call at
execution time — grounded in the actual current file contents recorded by
the preceding read step — to produce the complete new file.
"""

from __future__ import annotations

from .ai import AIAdapter, AIMessage, AIRequest
from .errors import ProviderError
from .planning import PlanStep

MATERIALIZE_SYSTEM = (
    "You are Stratum's file editor. Given the current content of a file and "
    "the approved change summary, output ONLY the complete new file content. "
    "No explanations, no code fences, no commentary."
)


def build_materialize_request(
    *,
    step: PlanStep,
    task_description: str,
    path: str,
    current_content: str | None,
) -> AIRequest:
    assert step.action_type == "write_file"
    parts = [
        f"# Task\n{task_description}",
        f"# Approved change for {path}\n{step.content_summary or step.description}",
        "# Current file content\n```",
        current_content if current_content is not None else "(new file)",
        "```",
        "# Output\nThe complete new content of the file.",
    ]
    return AIRequest(
        model="",
        messages=(
            AIMessage(role="system", content=MATERIALIZE_SYSTEM),
            AIMessage(role="user", content="\n\n".join(parts)),
        ),
        temperature=0.0,
        max_tokens=8192,
        metadata={"purpose": "materialize_write", "path": path},
    )


def extract_content(response_text: str) -> str:
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop opening fence (and optional language tag) and closing fence.
        if len(lines) >= 2 and lines[-1].strip().startswith("```"):
            body = "\n".join(lines[1:-1])
            return body + "\n" if response_text.endswith("\n") else body
        raise ProviderError("model returned an unterminated code fence")
    return response_text


async def materialize_write(
    adapter: AIAdapter,
    *,
    model: str,
    step: PlanStep,
    task_description: str,
    path: str,
    current_content: str | None,
) -> tuple[str, object]:
    request = build_materialize_request(
        step=step,
        task_description=task_description,
        path=path,
        current_content=current_content,
    )
    request = AIRequest(
        model=model,
        messages=request.messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        metadata=request.metadata,
    )
    response = await adapter.generate(request)
    return extract_content(response.content), response
