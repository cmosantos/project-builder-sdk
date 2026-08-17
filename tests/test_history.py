import json
from pathlib import Path

from rich.console import Console

from project_builder.orchestration.history import (
    BUILD_HISTORY_SCHEMA_VERSION,
    build_history_panel,
    collect_build_history,
    format_history_summary,
    write_build_history_index,
)


def manifest_payload(
    *,
    build_id: str,
    generated_at: str,
    stage: str = "completed",
    qa_score: int = 98,
    runtime_quality: str = "HEALTHY",
    health: str = "HEALTHY",
    policy: str = "PASS",
    duration_ms: float = 60_000.0,
    tokens: int = 20_000,
    requests: int = 6,
    repairs: int = 0,
    tests_passed: int = 16,
    warnings: int = 0,
    policy_violations: int = 0,
) -> dict:
    return {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "build": {
            "build_id": build_id,
            "stage": stage,
            "repairs": repairs,
        },
        "qa": {
            "score": qa_score,
        },
        "runtime": {
            "quality": {
                "status": runtime_quality,
                "passed_count": tests_passed,
                "warning_count": warnings,
            },
        },
        "health": {
            "status": health,
        },
        "policy": {
            "status": policy,
            "violation_count": policy_violations,
        },
        "usage": {
            "totals": {
                "requests": requests,
                "total_tokens": tokens,
            },
        },
        "performance": {
            "total_duration_ms": duration_ms,
        },
    }


def write_manifest(
    root: Path,
    payload: dict,
) -> Path:
    build_id = payload[
        "build"
    ][
        "build_id"
    ]

    path = (
        root
        / build_id
        / "build_manifest.json"
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload
        ),
        encoding="utf-8",
    )

    return path


def test_collect_history_orders_newest_first(
    tmp_path: Path,
):
    root = (
        tmp_path
        / "evidence"
    )

    write_manifest(
        root,
        manifest_payload(
            build_id="build-old",
            generated_at="2026-08-14T10:00:00+00:00",
        ),
    )

    write_manifest(
        root,
        manifest_payload(
            build_id="build-new",
            generated_at="2026-08-14T12:00:00+00:00",
        ),
    )

    entries, skipped = collect_build_history(
        root
    )

    assert (
        entries[
            0
        ].build_id
        == "build-new"
    )

    assert (
        entries[
            1
        ].build_id
        == "build-old"
    )

    assert skipped == 0


def test_collect_history_extracts_compact_metrics(
    tmp_path: Path,
):
    root = (
        tmp_path
        / "evidence"
    )

    write_manifest(
        root,
        manifest_payload(
            build_id="build-1",
            generated_at="2026-08-14T10:00:00+00:00",
            qa_score=97,
            runtime_quality="ATTENTION",
            health="ATTENTION",
            policy="VIOLATION",
            duration_ms=92_200.0,
            tokens=38_132,
            requests=9,
            repairs=1,
            tests_passed=18,
            warnings=2,
            policy_violations=1,
        ),
    )

    entries, _ = collect_build_history(
        root
    )

    entry = entries[
        0
    ]

    assert entry.qa_score == 97
    assert entry.runtime_quality == "ATTENTION"
    assert entry.health == "ATTENTION"
    assert entry.policy == "VIOLATION"
    assert entry.duration_seconds == 92.2
    assert entry.tokens == 38_132
    assert entry.requests == 9
    assert entry.repairs == 1
    assert entry.tests_passed == 18
    assert entry.warnings == 2
    assert entry.policy_violations == 1


def test_invalid_manifest_is_skipped(
    tmp_path: Path,
):
    root = (
        tmp_path
        / "evidence"
    )

    write_manifest(
        root,
        manifest_payload(
            build_id="build-valid",
            generated_at="2026-08-14T10:00:00+00:00",
        ),
    )

    broken = (
        root
        / "broken"
        / "build_manifest.json"
    )

    broken.parent.mkdir(
        parents=True
    )

    broken.write_text(
        "{broken-json",
        encoding="utf-8",
    )

    entries, skipped = collect_build_history(
        root
    )

    assert len(
        entries
    ) == 1

    assert skipped == 1


def test_manifest_without_build_id_is_skipped(
    tmp_path: Path,
):
    root = (
        tmp_path
        / "evidence"
    )

    payload = manifest_payload(
        build_id="temporary",
        generated_at="2026-08-14T10:00:00+00:00",
    )

    payload[
        "build"
    ].pop(
        "build_id"
    )

    path = (
        root
        / "broken"
        / "build_manifest.json"
    )

    path.parent.mkdir(
        parents=True
    )

    path.write_text(
        json.dumps(
            payload
        ),
        encoding="utf-8",
    )

    entries, skipped = collect_build_history(
        root
    )

    assert entries == ()
    assert skipped == 1


def test_write_history_index_contains_all_valid_builds(
    tmp_path: Path,
):
    root = (
        tmp_path
        / "evidence"
    )

    write_manifest(
        root,
        manifest_payload(
            build_id="build-1",
            generated_at="2026-08-14T10:00:00+00:00",
        ),
    )

    current = write_manifest(
        root,
        manifest_payload(
            build_id="build-2",
            generated_at="2026-08-14T11:00:00+00:00",
        ),
    )

    result = write_build_history_index(
        current
    )

    assert result.status == "INDEXED"
    assert result.total_builds == 2
    assert result.path.is_file()

    payload = json.loads(
        result.path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        payload[
            "schema_version"
        ]
        == BUILD_HISTORY_SCHEMA_VERSION
    )

    assert payload[
        "total_builds"
    ] == 2

    assert len(
        payload[
            "builds"
        ]
    ) == 2


def test_history_index_is_rebuilt_not_duplicated(
    tmp_path: Path,
):
    root = (
        tmp_path
        / "evidence"
    )

    current = write_manifest(
        root,
        manifest_payload(
            build_id="build-1",
            generated_at="2026-08-14T10:00:00+00:00",
        ),
    )

    first = write_build_history_index(
        current
    )

    second = write_build_history_index(
        current
    )

    assert first.total_builds == 1
    assert second.total_builds == 1

    payload = json.loads(
        second.path.read_text(
            encoding="utf-8"
        )
    )

    assert len(
        payload[
            "builds"
        ]
    ) == 1


def test_history_index_ignores_its_own_json_file(
    tmp_path: Path,
):
    root = (
        tmp_path
        / "evidence"
    )

    current = write_manifest(
        root,
        manifest_payload(
            build_id="build-1",
            generated_at="2026-08-14T10:00:00+00:00",
        ),
    )

    result = write_build_history_index(
        current
    )

    result2 = write_build_history_index(
        current
    )

    assert result2.total_builds == 1


def test_summary_and_panel_render(
    tmp_path: Path,
):
    root = (
        tmp_path
        / "evidence"
    )

    current = write_manifest(
        root,
        manifest_payload(
            build_id="project-builder-1234567890abcdef",
            generated_at="2026-08-14T10:00:00+00:00",
        ),
    )

    result = write_build_history_index(
        current
    )

    summary = format_history_summary(
        result
    )

    assert "INDEXED" in summary
    assert "1 builds" in summary

    panel = build_history_panel(
        result
    )

    console = Console(
        record=True,
        width=180,
    )

    console.print(
        panel
    )

    output = console.export_text()

    assert "BUILD HISTORY" in output
    assert "HEALTHY" in output
    assert "PASS" in output
    assert "20.000" in output