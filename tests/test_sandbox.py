from pathlib import Path
import sys

import pytest

from project_builder.sandbox import (
    SandboxExecutor,
    SandboxPolicy,
)


def test_policy_rejects_unknown_operation() -> None:
    policy = SandboxPolicy()

    with pytest.raises(ValueError):
        policy.build_arguments(
            "powershell"
        )


def test_policy_rejects_excessive_timeout() -> None:
    policy = SandboxPolicy()

    with pytest.raises(ValueError):
        policy.validate_timeout(
            policy.max_timeout_seconds + 1
        )


def test_sandbox_uses_temporary_copy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "workspace"
    root = tmp_path / ".sandbox"

    source.mkdir()
    original = source / "sample.txt"
    original.write_text(
        "original",
        encoding="utf-8",
    )

    with SandboxExecutor(
        source_workspace=source,
        sandbox_root=root,
        python_executable=sys.executable,
    ) as sandbox:
        assert sandbox.workspace is not None

        copied = (
            sandbox.workspace
            / "sample.txt"
        )

        assert copied.read_text(
            encoding="utf-8"
        ) == "original"

        copied.write_text(
            "alterado no sandbox",
            encoding="utf-8",
        )

        assert original.read_text(
            encoding="utf-8"
        ) == "original"

        run_path = sandbox.workspace

    assert not run_path.exists()


def test_sandbox_runs_only_policy_operation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "workspace"
    root = tmp_path / ".sandbox"

    app = source / "app"
    app.mkdir(
        parents=True
    )

    (app / "__init__.py").write_text(
        "",
        encoding="utf-8",
    )

    (app / "main.py").write_text(
        "class FakeApp: pass\napp = FakeApp()\n",
        encoding="utf-8",
    )

    with SandboxExecutor(
        source_workspace=source,
        sandbox_root=root,
        python_executable=sys.executable,
    ) as sandbox:
        result = sandbox.run(
            "smoke_test",
            timeout=10,
        )

    assert result.success is True
    assert "FASTAPI APP OK" in result.stdout
    assert "FakeApp" in result.stdout