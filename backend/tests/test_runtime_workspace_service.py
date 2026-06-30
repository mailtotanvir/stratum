from pathlib import Path

import pytest

from app.services.runtime_workspace_service import RuntimeWorkspaceService


def test_register_workspace(tmp_path) -> None:
    workspace = RuntimeWorkspaceService(tmp_path)
    other = tmp_path / "other"
    other.mkdir()

    registered = workspace.register_workspace("other", other)

    assert registered.name == "other"
    assert registered.root_path == other.resolve().as_posix()
    assert registered.active is False
    assert workspace.get_active_workspace().root_path == tmp_path.resolve().as_posix()


def test_duplicate_root_rejected(tmp_path) -> None:
    workspace = RuntimeWorkspaceService(tmp_path)

    with pytest.raises(ValueError, match="already registered"):
        workspace.register_workspace("duplicate", tmp_path)


def test_invalid_path_rejected(tmp_path) -> None:
    workspace = RuntimeWorkspaceService(tmp_path)
    missing = tmp_path / "missing"

    with pytest.raises(ValueError, match="does not exist"):
        workspace.register_workspace("missing", missing)

    file_path = tmp_path / "file.txt"
    file_path.write_text("value", encoding="utf-8")

    with pytest.raises(ValueError, match="not a directory"):
        workspace.register_workspace("file", file_path)


def test_activate_workspace(tmp_path) -> None:
    workspace = RuntimeWorkspaceService(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    registered = workspace.register_workspace("other", other)

    active = workspace.set_active_workspace(registered.workspace_id)

    assert active.active is True
    assert workspace.get_active_workspace().workspace_id == registered.workspace_id
    assert workspace.get_workspace(registered.workspace_id).active is True
    assert workspace.get_workspace(active.workspace_id).active is True


def test_deterministic_ordering(tmp_path) -> None:
    workspace = RuntimeWorkspaceService(tmp_path)
    alpha = tmp_path / "alpha"
    alpha.mkdir()
    beta = tmp_path / "beta"
    beta.mkdir()
    workspace.register_workspace("beta", beta)
    workspace.register_workspace("alpha", alpha)

    assert [item.name for item in workspace.list_workspaces()] == [
        "alpha",
        "beta",
        "default",
    ]

