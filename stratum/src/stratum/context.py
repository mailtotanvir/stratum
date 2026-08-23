"""Deterministic, bounded repository context loading.

Builds the factual input the planner receives. Explicit and bounded:
repository metadata, git state, a depth-limited file tree summary, selected
text files, and optional operator-provided markdown. Never dumps a whole
repository into the model.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .errors import RepositoryError

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "target",
}

MAX_FILE_BYTES = 20_000
DEFAULT_CONTEXT_BUDGET = 24_000
TREE_MAX_ENTRIES = 200
TREE_MAX_DEPTH = 4


@dataclass(frozen=True)
class GitInfo:
    is_repo: bool = False
    branch: str | None = None
    head: str | None = None
    status: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "is_repo": self.is_repo,
            "branch": self.branch,
            "head": self.head,
            "status": self.status,
        }


@dataclass
class RepoContext:
    root: Path
    git: GitInfo
    tree_summary: list[str] = field(default_factory=list)
    selected_files: dict[str, str] = field(default_factory=dict)
    markdown_context: str = ""
    task_description: str = ""


def _run_git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def collect_git_info(repo: Path) -> GitInfo:
    if _run_git(repo, "rev-parse", "--is-inside-work-tree") != "true":
        return GitInfo(is_repo=False)
    branch = _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    head = _run_git(repo, "rev-parse", "HEAD")
    status = _run_git(repo, "status", "--porcelain") or ""
    return GitInfo(is_repo=True, branch=branch, head=head, status=status)


def build_tree_summary(root: Path) -> list[str]:
    entries: list[str] = []

    def walk(directory: Path, prefix: str, depth: int) -> None:
        if depth > TREE_MAX_DEPTH or len(entries) >= TREE_MAX_ENTRIES:
            return
        try:
            children = sorted(
                directory.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
        except OSError:
            return
        for child in children:
            if len(entries) >= TREE_MAX_ENTRIES:
                entries.append("... (truncated)")
                return
            if child.is_dir():
                if child.name in IGNORED_DIRS or child.name.startswith("."):
                    continue
                entries.append(f"{prefix}{child.name}/")
                walk(child, f"{prefix}{child.name}/", depth + 1)
            else:
                entries.append(f"{prefix}{child.name}")

    walk(root, "", 1)
    return entries


def read_text_file(path: Path, *, max_bytes: int = MAX_FILE_BYTES) -> str:
    raw = path.read_bytes()[:max_bytes]
    return raw.decode("utf-8", errors="replace")


def load_repository_context(
    *,
    repo_path: Path,
    task_description: str,
    selected_files: list[str] | None = None,
    markdown_context: str = "",
) -> RepoContext:
    repo = Path(repo_path).expanduser().resolve()
    if not repo.is_dir():
        raise RepositoryError(f"repository path does not exist: {repo}")

    git = collect_git_info(repo)

    tree = build_tree_summary(repo)

    contents: dict[str, str] = {}
    for rel in selected_files or []:
        candidate = (repo / rel).resolve()
        if not candidate.is_relative_to(repo):
            raise RepositoryError(f"selected file escapes repository: {rel}")
        if not candidate.is_file():
            raise RepositoryError(f"selected file does not exist: {rel}")
        contents[rel] = read_text_file(candidate)

    return RepoContext(
        root=repo,
        git=git,
        tree_summary=tree,
        selected_files=contents,
        markdown_context=markdown_context or "",
        task_description=task_description,
    )


def render_prompt_context(ctx: RepoContext, budget: int = DEFAULT_CONTEXT_BUDGET) -> str:
    """Render the bounded context as prompt text within a character budget."""
    sections: list[str] = []

    sections.append(f"Repository root: {ctx.root}")
    if ctx.git.is_repo:
        sections.append(f"Git branch: {ctx.git.branch}")
        sections.append(f"Git HEAD: {ctx.git.head}")
        if ctx.git.status:
            lines = ctx.git.status.splitlines()
            shown = "\n".join(lines[:30])
            more = f"\n... ({len(lines)} total)" if len(lines) > 30 else ""
            sections.append(f"Git status:\n{shown}{more}")
    else:
        sections.append("Git: not a repository")

    if ctx.tree_summary:
        sections.append("File tree:\n" + "\n".join(ctx.tree_summary))

    for rel, content in ctx.selected_files.items():
        sections.append(f"--- File: {rel} ---\n{content}")

    if ctx.markdown_context.strip():
        sections.append(f"--- Operator context ---\n{ctx.markdown_context.strip()}")

    joined = "\n\n".join(sections)
    if len(joined) <= budget:
        return joined

    # Drop the largest optional sections until we fit; never truncate the
    # task description silently.
    trimmed = sections[:]
    while len(joined) > budget and len(trimmed) > 2:
        largest_idx = max(
            range(2, len(trimmed)), key=lambda i: len(trimmed[i]), default=-1
        )
        if largest_idx < 0:
            break
        del trimmed[largest_idx]
        joined = "\n\n".join(trimmed)
    if len(joined) > budget:
        joined = joined[:budget]
    return joined
