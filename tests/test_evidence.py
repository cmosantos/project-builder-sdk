import json
from pathlib import Path
from types import SimpleNamespace

from project_builder.orchestration.evidence import (
    BUILD_EVIDENCE_SCHEMA_VERSION,
    build_evidence_manifest,
    evidence_path_for,
    write_build_manifest,
)
from project_builder.orchestration.state import (
    AgentUsageMetric,
    ExecutionEvent,
    ProjectStage,
    ProjectState,
)


EXPECTED_FILES = (
    "app/__init__.py",
    "app/main.py",
    "tests/test_api.py",
)


def make_state() -> ProjectState:
    state = ProjectState(
        request="Crie uma API FastAPI"
    )

    state.build_id = (
        "project-builder-test123"
    )

    state.stage = (
        ProjectStage.COMPLETED
    )

    state.request_gate_status = (
        "IMPLEMENTABLE"
    )

    state.request_gate_reason = (
        "Pedido compatível."
    )

    state.context = SimpleNamespace(
        qa_report=SimpleNamespace(
            status="APROVADO",
            score=98,
        ),
        runtime_report=SimpleNamespace(
            status="APROVADO",
            smoke_test=SimpleNamespace(
                comando="smoke",
                sucesso=True,
            ),
            pytest=SimpleNamespace(
                comando="pytest",
                sucesso=True,
                stdout="16 passed in 0.42s",
                stderr="",
            ),
            http_check=SimpleNamespace(
                comando="http live",
                sucesso=True,
            ),
        ),
    )

    state.handoff_history.extend(
        [
            "Project Router -> Project Architect",
            "Project Architect -> Project Developer",
        ]
    )

    state.transition_history.extend(
        [
            "created -> request_validation",
            "request_validation -> routing",
            "routing -> development",
            "development -> qa",
            "qa -> runtime",
            "runtime -> completed",
        ]
    )

    state.execution_events.extend(
        [
            ExecutionEvent(
                sequence=1,
                event_type="agent_activated",
                stage="development",
                elapsed_ms=1_000.0,
                target="Project Developer",
            ),
            ExecutionEvent(
                sequence=2,
                event_type="stage_transition",
                stage="qa",
                elapsed_ms=20_000.0,
                source="development",
                target="qa",
                details={
                    "ok": True,
                },
            ),
        ]
    )

    state.agent_usage.append(
        AgentUsageMetric(
            sequence=1,
            agent_name="Project Developer",
            stage="development",
            requests=2,
            input_tokens=8_000,
            output_tokens=2_000,
            total_tokens=10_000,
            cached_tokens=1_000,
            reasoning_tokens=100,
        )
    )

    state.runtime_history.append(
        {
            "attempt": 1,
            "report_status": "APROVADO",
            "quality_status": "HEALTHY",
            "warning_count": 0,
            "warning_detected": False,
        }
    )

    return state


def make_workspace(
    root: Path,
) -> Path:
    workspace = (
        root
        / "workspace"
    )

    (
        workspace
        / "app"
    ).mkdir(
        parents=True
    )

    (
        workspace
        / "tests"
    ).mkdir(
        parents=True
    )

    (
        workspace
        / "app"
        / "__init__.py"
    ).write_text(
        "",
        encoding="utf-8",
    )

    (
        workspace
        / "app"
        / "main.py"
    ).write_text(
        "print('ok')\n",
        encoding="utf-8",
    )

    (
        workspace
        / "tests"
        / "test_api.py"
    ).write_text(
        "def test_ok(): assert True\n",
        encoding="utf-8",
    )

    return workspace


def test_manifest_contains_core_sections(
    tmp_path: Path,
):
    state = make_state()

    workspace = make_workspace(
        tmp_path
    )

    manifest = build_evidence_manifest(
        state,
        workspace_root=workspace,
        expected_files=EXPECTED_FILES,
        sandbox_cleanup_ok=True,
    )

    assert (
        manifest[
            "schema_version"
        ]
        == BUILD_EVIDENCE_SCHEMA_VERSION
    )

    assert (
        manifest[
            "build"
        ][
            "build_id"
        ]
        == state.build_id
    )

    assert (
        manifest[
            "qa"
        ][
            "status"
        ]
        == "APROVADO"
    )

    assert (
        manifest[
            "runtime"
        ][
            "quality"
        ][
            "status"
        ]
        == "HEALTHY"
    )

    assert (
        manifest[
            "health"
        ][
            "status"
        ]
        == "HEALTHY"
    )

    assert (
        manifest[
            "policy"
        ][
            "status"
        ]
        == "PASS"
    )


def test_manifest_records_usage_performance_and_flow(
    tmp_path: Path,
):
    state = make_state()

    workspace = make_workspace(
        tmp_path
    )

    manifest = build_evidence_manifest(
        state,
        workspace_root=workspace,
        expected_files=EXPECTED_FILES,
        sandbox_cleanup_ok=True,
    )

    assert (
        manifest[
            "usage"
        ][
            "totals"
        ][
            "total_tokens"
        ]
        == 10_000
    )

    assert (
        manifest[
            "performance"
        ][
            "highest_usage_agent"
        ]
        == "Project Developer"
    )

    assert (
        manifest[
            "flow"
        ][
            "handoffs"
        ]
        == state.handoff_history
    )

    assert (
        len(
            manifest[
                "flow"
            ][
                "timeline"
            ]
        )
        == 2
    )


def test_manifest_hashes_workspace_artifacts(
    tmp_path: Path,
):
    state = make_state()

    workspace = make_workspace(
        tmp_path
    )

    manifest = build_evidence_manifest(
        state,
        workspace_root=workspace,
        expected_files=EXPECTED_FILES,
        sandbox_cleanup_ok=True,
    )

    files = {
        item[
            "path"
        ]: item
        for item in manifest[
            "artifacts"
        ][
            "files"
        ]
    }

    assert (
        files[
            "app/main.py"
        ][
            "exists"
        ]
        is True
    )

    assert (
        len(
            files[
                "app/main.py"
            ][
                "sha256"
            ]
        )
        == 64
    )

    assert (
        files[
            "app/main.py"
        ][
            "size_bytes"
        ]
        > 0
    )


def test_manifest_represents_missing_artifact(
    tmp_path: Path,
):
    state = make_state()

    workspace = make_workspace(
        tmp_path
    )

    missing_path = (
        workspace
        / "tests"
        / "test_api.py"
    )

    missing_path.unlink()

    manifest = build_evidence_manifest(
        state,
        workspace_root=workspace,
        expected_files=EXPECTED_FILES,
        sandbox_cleanup_ok=True,
    )

    files = {
        item[
            "path"
        ]: item
        for item in manifest[
            "artifacts"
        ][
            "files"
        ]
    }

    missing = files[
        "tests/test_api.py"
    ]

    assert (
        missing[
            "exists"
        ]
        is False
    )

    assert (
        missing[
            "sha256"
        ]
        is None
    )

    assert (
        manifest[
            "artifacts"
        ][
            "present"
        ]
        == 2
    )


def test_artifact_hash_changes_when_file_changes(
    tmp_path: Path,
):
    state = make_state()

    workspace = make_workspace(
        tmp_path
    )

    first = build_evidence_manifest(
        state,
        workspace_root=workspace,
        expected_files=EXPECTED_FILES,
        sandbox_cleanup_ok=True,
    )

    main_path = (
        workspace
        / "app"
        / "main.py"
    )

    main_path.write_text(
        "print('changed')\n",
        encoding="utf-8",
    )

    second = build_evidence_manifest(
        state,
        workspace_root=workspace,
        expected_files=EXPECTED_FILES,
        sandbox_cleanup_ok=True,
    )

    first_hash = next(
        item[
            "sha256"
        ]
        for item in first[
            "artifacts"
        ][
            "files"
        ]
        if item[
            "path"
        ]
        == "app/main.py"
    )

    second_hash = next(
        item[
            "sha256"
        ]
        for item in second[
            "artifacts"
        ][
            "files"
        ]
        if item[
            "path"
        ]
        == "app/main.py"
    )

    assert (
        first_hash
        != second_hash
    )


def test_write_manifest_creates_versioned_evidence_path(
    tmp_path: Path,
):
    state = make_state()

    workspace = make_workspace(
        tmp_path
    )

    evidence_root = (
        tmp_path
        / ".project_builder"
        / "evidence"
    )

    result = write_build_manifest(
        state,
        workspace_root=workspace,
        expected_files=EXPECTED_FILES,
        sandbox_cleanup_ok=True,
        evidence_root=evidence_root,
    )

    assert (
        result.status
        == "WRITTEN"
    )

    assert (
        result.path
        == (
            evidence_root
            / state.build_id
            / "build_manifest.json"
        ).resolve()
    )

    assert (
        result.path.is_file()
    )

    assert (
        len(
            result.sha256
        )
        == 64
    )

    assert (
        result.size_bytes
        > 0
    )

    loaded = json.loads(
        result.path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        loaded[
            "build"
        ][
            "build_id"
        ]
        == state.build_id
    )


def test_evidence_path_rejects_unsafe_build_id(
    tmp_path: Path,
):
    state = make_state()

    state.build_id = (
        "../escape"
    )

    try:
        evidence_path_for(
            state,
            evidence_root=tmp_path,
        )

    except ValueError as exc:
        assert (
            "caracteres inválidos"
            in str(
                exc
            )
        )

    else:
        raise AssertionError(
            "Build ID inseguro deveria ser rejeitado."
        )


def test_manifest_preserves_policy_violation_as_evidence(
    tmp_path: Path,
):
    state = make_state()

    workspace = make_workspace(
        tmp_path
    )

    state.agent_usage.append(
        AgentUsageMetric(
            sequence=2,
            agent_name="Project QA",
            stage="qa",
            requests=1,
            input_tokens=45_000,
            output_tokens=5_000,
            total_tokens=50_000,
        )
    )

    manifest = build_evidence_manifest(
        state,
        workspace_root=workspace,
        expected_files=EXPECTED_FILES,
        sandbox_cleanup_ok=True,
    )

    assert (
        manifest[
            "policy"
        ][
            "status"
        ]
        == "VIOLATION"
    )

    assert (
        manifest[
            "policy"
        ][
            "violation_count"
        ]
        >= 1
    )