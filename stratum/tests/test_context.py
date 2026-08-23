from pathlib import Path

import pytest

from stratum.context import (
    collect_git_info,
    load_repository_context,
    render_prompt_context,
)
from stratum.errors import RepositoryError


def test_rejects_missing_path(tmp_path):
    with pytest.raises(RepositoryError, match="does not exist"):
        load_repository_context(
            repo_path=tmp_path / "nope", task_description="t")


def test_detects_git_and_builds_tree(git_repo: Path):
    ctx = load_repository_context(repo_path=git_repo, task_description="t")
    assert ctx.git.is_repo
    assert ctx.git.branch == "main" or ctx.git.branch == "master"
    assert "hello.py" in ctx.tree_summary
    assert "test_hello.py" in ctx.tree_summary
    assert ctx.git.status == ""  # clean fixture


def test_selected_files_are_loaded_and_bounded(git_repo: Path):
    ctx = load_repository_context(
        repo_path=git_repo, task_description="t", selected_files=["hello.py"])
    assert 'return "Hello"' in ctx.selected_files["hello.py"]


def test_selected_file_must_exist(git_repo: Path):
    with pytest.raises(RepositoryError, match="does not exist"):
        load_repository_context(
            repo_path=git_repo, task_description="t", selected_files=["ghost.py"])


def test_selected_file_cannot_escape(git_repo: Path):
    with pytest.raises(RepositoryError, match="escapes repository"):
        load_repository_context(
            repo_path=git_repo, task_description="t", selected_files=["../x.py"])


def test_render_prompt_contains_sections(git_repo: Path):
    ctx = load_repository_context(
        repo_path=git_repo,
        task_description="change greeting",
        selected_files=["hello.py"],
        markdown_context="# Spec\nUse Hello Stratum.",
    )
    prompt = render_prompt_context(ctx)
    assert "Git branch" in prompt
    assert "hello.py" in prompt
    assert "# Spec" in prompt


def test_render_prompt_respects_budget(git_repo: Path):
    big = git_repo / "big.txt"
    big.write_text("x" * 50_000, encoding="utf-8")
    ctx = load_repository_context(
        repo_path=git_repo,
        task_description="t",
        selected_files=["big.txt", "hello.py"],
    )
    prompt = render_prompt_context(ctx, budget=5_000)
    assert len(prompt) <= 5_000 + 200  # small slack for section joins
