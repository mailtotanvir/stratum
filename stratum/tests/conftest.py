from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

HELLO_INITIAL = '''def greeting():
    return "Hello"


if __name__ == "__main__":
    print(greeting())
'''

TEST_INITIAL = '''from hello import greeting


def test_greeting():
    assert greeting() == "Hello"
'''


def make_git_repo(tmp_path: Path) -> Path:
    """Create a real disposable git repository with the benchmark fixture."""
    repo = tmp_path / "example-repo"
    repo.mkdir()
    (repo / "hello.py").write_text(HELLO_INITIAL, encoding="utf-8")
    (repo / "test_hello.py").write_text(TEST_INITIAL, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=stratum@example.com",
         "-c", "user.name=Stratum Fixture", "commit", "-qm", "fixture init"],
        cwd=repo,
        check=True,
    )
    return repo


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    return make_git_repo(tmp_path)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "stratum-data"
    d.mkdir()
    return d
