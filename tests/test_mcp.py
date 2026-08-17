import os
from pathlib import Path

import pytest

from project_builder.mcp.workspace_server import (
    _list_workspace_files,
    _read_workspace_file,
    _resolve_relative,
    _search_workspace_text,
    _workspace_snapshot,
)


@pytest.fixture
def mcp_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "app").mkdir()

    (workspace / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n",
        encoding="utf-8",
    )

    (workspace / "README.md").write_text(
        "Projeto Builder MCP\n",
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "PROJECT_BUILDER_MCP_WORKSPACE",
        str(workspace),
    )

    return workspace


def test_mcp_lists_workspace(
    mcp_workspace: Path,
) -> None:
    files = _list_workspace_files()

    assert files == [
        "README.md",
        "app/main.py",
    ]


def test_mcp_reads_relative_file(
    mcp_workspace: Path,
) -> None:
    content = _read_workspace_file(
        "app/main.py"
    )

    assert "FastAPI" in content


def test_mcp_blocks_path_escape(
    mcp_workspace: Path,
) -> None:
    with pytest.raises(ValueError):
        _resolve_relative(
            "../fora.txt"
        )


def test_mcp_searches_workspace(
    mcp_workspace: Path,
) -> None:
    matches = _search_workspace_text(
        "FastAPI"
    )

    assert matches
    assert matches[0]["file"] == "app/main.py"


def test_mcp_snapshot_returns_all_files(
    mcp_workspace: Path,
) -> None:
    snapshot = _workspace_snapshot()

    assert snapshot["mode"] == "read-only"
    assert snapshot["file_count"] == 2

    files = {
        item["path"]: item["content"]
        for item in snapshot["files"]
    }

    assert set(files) == {
        "README.md",
        "app/main.py",
    }
    assert "FastAPI" in files["app/main.py"]


def test_mcp_snapshot_is_read_only(
    mcp_workspace: Path,
) -> None:
    before = (
        mcp_workspace / "README.md"
    ).read_text(encoding="utf-8")

    _workspace_snapshot()

    after = (
        mcp_workspace / "README.md"
    ).read_text(encoding="utf-8")

    assert after == before
