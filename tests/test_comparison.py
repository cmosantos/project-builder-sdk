import json
from pathlib import Path

from rich.console import Console

from project_builder.orchestration.comparison import (
    build_comparison_panel,
    compare_with_previous_manifest,
    find_previous_manifest,
    format_comparison_summary,
)


def manifest_payload(
    *,
    build_id: str,
    generated_at: str,
    duration_ms: float = 60_000.0,
    tokens: int = 20_000,
    requests: int = 6,
    qa_score: int = 95,
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
            "repairs": repairs,
        },
        "qa": {
            "score": qa_score,
        },
        "runtime": {
            "quality": {
                "passed_count": tests_passed,
                "warning_count": warnings,
            },
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
        "policy": {
            "violation_count": policy_violations,
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


def test_find_previous_manifest_uses_latest_earlier_build(
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

    expected = write_manifest(
        root,
        manifest_payload(
            build_id="build-2",
            generated_at="2026-08-14T11:00:00+00:00",
        ),
    )

    current = write_manifest(
        root,
        manifest_payload(
            build_id="build-3",
            generated_at="2026-08-14T12:00:00+00:00",
        ),
    )

    assert (
        find_previous_manifest(
            current
        )
        == expected.resolve()
    )


def test_compare_returns_eight_metrics(
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

    result = compare_with_previous_manifest(
        current
    )

    assert (
        result.status
        == "COMPARED"
    )

    assert (
        len(
            result.metrics
        )
        == 8
    )


def test_no_baseline_on_first_build(
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

    result = compare_with_previous_manifest(
        current
    )

    assert (
        result.status
        == "NO_BASELINE"
    )

    assert (
        result.baseline_manifest
        is None
    )


def test_duration_and_token_deltas_are_calculated(
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
            duration_ms=100_000.0,
            tokens=40_000,
        ),
    )

    current = write_manifest(
        root,
        manifest_payload(
            build_id="build-2",
            generated_at="2026-08-14T11:00:00+00:00",
            duration_ms=80_000.0,
            tokens=50_000,
        ),
    )

    result = compare_with_previous_manifest(
        current
    )

    metrics = {
        metric.code: metric
        for metric in result.metrics
    }

    assert (
        metrics[
            "duration"
        ].delta
        == -20_000.0
    )

    assert (
        metrics[
            "duration"
        ].trend
        == "DOWN"
    )

    assert (
        metrics[
            "tokens"
        ].delta
        == 10_000.0
    )

    assert (
        metrics[
            "tokens"
        ].trend
        == "UP"
    )


def test_comparison_tracks_quality_and_policy_metrics(
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
            qa_score=90,
            repairs=1,
            tests_passed=12,
            warnings=4,
            policy_violations=1,
        ),
    )

    current = write_manifest(
        root,
        manifest_payload(
            build_id="build-2",
            generated_at="2026-08-14T11:00:00+00:00",
            qa_score=97,
            repairs=0,
            tests_passed=18,
            warnings=0,
            policy_violations=0,
        ),
    )

    result = compare_with_previous_manifest(
        current
    )

    metrics = {
        metric.code: metric
        for metric in result.metrics
    }

    assert (
        metrics[
            "qa_score"
        ].delta
        == 7.0
    )

    assert (
        metrics[
            "repairs"
        ].delta
        == -1.0
    )

    assert (
        metrics[
            "tests_passed"
        ].delta
        == 6.0
    )

    assert (
        metrics[
            "warnings"
        ].delta
        == -4.0
    )

    assert (
        metrics[
            "policy_violations"
        ].delta
        == -1.0
    )


def test_invalid_manifest_is_ignored_as_baseline(
    tmp_path: Path,
):
    root = (
        tmp_path
        / "evidence"
    )

    invalid = (
        root
        / "broken"
        / "build_manifest.json"
    )

    invalid.parent.mkdir(
        parents=True
    )

    invalid.write_text(
        "{not-json",
        encoding="utf-8",
    )

    valid = write_manifest(
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

    assert (
        find_previous_manifest(
            current
        )
        == valid.resolve()
    )


def test_future_manifest_is_not_used_as_baseline(
    tmp_path: Path,
):
    root = (
        tmp_path
        / "evidence"
    )

    expected = write_manifest(
        root,
        manifest_payload(
            build_id="build-old",
            generated_at="2026-08-14T10:00:00+00:00",
        ),
    )

    current = write_manifest(
        root,
        manifest_payload(
            build_id="build-current",
            generated_at="2026-08-14T11:00:00+00:00",
        ),
    )

    write_manifest(
        root,
        manifest_payload(
            build_id="build-future",
            generated_at="2026-08-14T12:00:00+00:00",
        ),
    )

    assert (
        find_previous_manifest(
            current
        )
        == expected.resolve()
    )


def test_summary_and_panel_render(
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
            tokens=25_000,
        ),
    )

    result = compare_with_previous_manifest(
        current
    )

    summary = format_comparison_summary(
        result
    )

    assert (
        "COMPARED"
        in summary
    )

    panel = build_comparison_panel(
        result
    )

    console = Console(
        record=True,
        width=160,
    )

    console.print(
        panel
    )

    output = console.export_text()

    assert (
        "BUILD COMPARISON"
        in output
    )

    assert (
        "Duration"
        in output
    )

    assert (
        "Tokens"
        in output
    )