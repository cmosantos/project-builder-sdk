from pathlib import Path

import pytest

import project_builder.workspace as workspace_module


def configurar_workspace_temporario(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, Path]:
    project_root = tmp_path / "project-builder"
    workspace_root = project_root / "workspace"

    workspace_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    monkeypatch.setattr(
        workspace_module,
        "PROJECT_ROOT",
        project_root,
    )

    monkeypatch.setattr(
        workspace_module,
        "WORKSPACE_ROOT",
        workspace_root,
    )

    return (
        project_root,
        workspace_root,
    )


def test_limpeza_preserva_contrato_e_remove_residuos(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, workspace = configurar_workspace_temporario(
        monkeypatch,
        tmp_path,
    )

    app = workspace / "app"
    tests = workspace / "tests"

    app.mkdir()
    tests.mkdir()

    arquivos_oficiais = {
        "app/__init__.py": "",
        "app/main.py": "main",
        "app/schemas.py": "schemas",
        "app/store.py": "store",
        "tests/test_api.py": "tests",
        "requirements.txt": "requirements",
        "README.md": "readme",
    }

    for relativo, conteudo in arquivos_oficiais.items():
        destino = workspace / relativo

        destino.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        destino.write_text(
            conteudo,
            encoding="utf-8",
        )

    # Residuos de uma execucao anterior.
    (workspace / "pytest.ini").write_text(
        "[pytest]\n",
        encoding="utf-8",
    )

    (app / "legacy.py").write_text(
        "legacy",
        encoding="utf-8",
    )

    (tests / "test_old.py").write_text(
        "old",
        encoding="utf-8",
    )

    cache = workspace / ".pytest_cache"
    cache.mkdir()

    (cache / "README.md").write_text(
        "cache",
        encoding="utf-8",
    )

    removidos = workspace_module.limpar_workspace()

    # Estrutura oficial continua existindo.
    assert app.is_dir()
    assert tests.is_dir()

    for relativo in arquivos_oficiais:
        assert (
            workspace / relativo
        ).is_file()

    # Residuos foram eliminados.
    assert not (
        workspace / "pytest.ini"
    ).exists()

    assert not (
        app / "legacy.py"
    ).exists()

    assert not (
        tests / "test_old.py"
    ).exists()

    assert not cache.exists()

    assert "pytest.ini" in removidos
    assert "app/legacy.py" in removidos
    assert "tests/test_old.py" in removidos
    assert ".pytest_cache/" in removidos


def test_limpeza_recusa_raiz_do_project_builder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project_root = (
        tmp_path
        / "project-builder"
    )

    project_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    monkeypatch.setattr(
        workspace_module,
        "PROJECT_ROOT",
        project_root,
    )

    monkeypatch.setattr(
        workspace_module,
        "WORKSPACE_ROOT",
        project_root,
    )

    with pytest.raises(
        RuntimeError,
        match="Workspace invalido",
    ):
        workspace_module.limpar_workspace()
