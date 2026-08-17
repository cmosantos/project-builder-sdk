from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


@dataclass(frozen=True)
class ComparisonMetric:
    code: str
    label: str
    current: float
    previous: float
    delta: float
    delta_percent: float | None
    trend: str
    format_kind: str


@dataclass(frozen=True)
class BuildComparisonResult:
    status: str
    current_build_id: str | None
    baseline_build_id: str | None
    current_manifest: Path
    baseline_manifest: Path | None
    metrics: tuple[ComparisonMetric, ...] = ()
    error: str | None = None


_METRICS = (
    (
        "duration",
        "Duration",
        ("performance", "total_duration_ms"),
        "milliseconds",
    ),
    (
        "tokens",
        "Tokens",
        ("usage", "totals", "total_tokens"),
        "integer",
    ),
    (
        "requests",
        "Requests",
        ("usage", "totals", "requests"),
        "integer",
    ),
    (
        "qa_score",
        "QA score",
        ("qa", "score"),
        "score",
    ),
    (
        "repairs",
        "Repairs",
        ("build", "repairs"),
        "integer",
    ),
    (
        "tests_passed",
        "Tests passed",
        ("runtime", "quality", "passed_count"),
        "integer",
    ),
    (
        "warnings",
        "Warnings",
        ("runtime", "quality", "warning_count"),
        "integer",
    ),
    (
        "policy_violations",
        "Policy violations",
        ("policy", "violation_count"),
        "integer",
    ),
)


def _parse_timestamp(
    value: object,
) -> datetime | None:
    if not isinstance(
        value,
        str,
    ):
        return None

    text = value.strip()

    if not text:
        return None

    if text.endswith(
        "Z"
    ):
        text = (
            text[:-1]
            + "+00:00"
        )

    try:
        return datetime.fromisoformat(
            text
        )
    except ValueError:
        return None


def _load_manifest(
    path: Path,
) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "Manifest deve conter um objeto JSON."
        )

    return payload


def _build_id(
    manifest: dict[str, Any],
) -> str | None:
    build = manifest.get(
        "build"
    )

    if not isinstance(
        build,
        dict,
    ):
        return None

    value = build.get(
        "build_id"
    )

    if value is None:
        return None

    return str(
        value
    )


def _nested_value(
    payload: dict[str, Any],
    path: tuple[str, ...],
) -> object:
    current: object = payload

    for key in path:
        if not isinstance(
            current,
            dict,
        ):
            return 0

        current = current.get(
            key,
            0,
        )

    return current


def _numeric_value(
    payload: dict[str, Any],
    path: tuple[str, ...],
) -> float:
    value = _nested_value(
        payload,
        path,
    )

    if value is None:
        return 0.0

    if isinstance(
        value,
        bool,
    ):
        return float(
            int(
                value
            )
        )

    try:
        return float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0.0


def find_previous_manifest(
    current_manifest: Path,
) -> Path | None:
    current_manifest = (
        current_manifest.resolve()
    )

    if not current_manifest.is_file():
        return None

    try:
        current_payload = _load_manifest(
            current_manifest
        )
    except (
        OSError,
        json.JSONDecodeError,
        ValueError,
    ):
        return None

    current_timestamp = _parse_timestamp(
        current_payload.get(
            "generated_at"
        )
    )

    evidence_root = (
        current_manifest
        .parent
        .parent
    )

    candidates: list[
        tuple[
            datetime,
            Path,
        ]
    ] = []

    for path in evidence_root.glob(
        "*/build_manifest.json"
    ):
        resolved = path.resolve()

        if resolved == current_manifest:
            continue

        try:
            payload = _load_manifest(
                resolved
            )
        except (
            OSError,
            json.JSONDecodeError,
            ValueError,
        ):
            continue

        timestamp = _parse_timestamp(
            payload.get(
                "generated_at"
            )
        )

        if timestamp is None:
            continue

        if (
            current_timestamp is not None
            and timestamp > current_timestamp
        ):
            continue

        candidates.append(
            (
                timestamp,
                resolved,
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return candidates[
        0
    ][
        1
    ]


def _build_metric(
    *,
    code: str,
    label: str,
    current: float,
    previous: float,
    format_kind: str,
) -> ComparisonMetric:
    delta = (
        current
        - previous
    )

    if delta > 0:
        trend = "UP"
    elif delta < 0:
        trend = "DOWN"
    else:
        trend = "SAME"

    if previous == 0:
        delta_percent = (
            0.0
            if current == 0
            else None
        )
    else:
        delta_percent = (
            delta
            / abs(
                previous
            )
            * 100.0
        )

    return ComparisonMetric(
        code=code,
        label=label,
        current=current,
        previous=previous,
        delta=delta,
        delta_percent=delta_percent,
        trend=trend,
        format_kind=format_kind,
    )


def compare_with_previous_manifest(
    current_manifest: Path,
) -> BuildComparisonResult:
    current_manifest = (
        current_manifest.resolve()
    )

    try:
        current = _load_manifest(
            current_manifest
        )
    except (
        OSError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        return BuildComparisonResult(
            status="FAILED",
            current_build_id=None,
            baseline_build_id=None,
            current_manifest=current_manifest,
            baseline_manifest=None,
            error=str(
                exc
            ),
        )

    current_build_id = _build_id(
        current
    )

    baseline_path = find_previous_manifest(
        current_manifest
    )

    if baseline_path is None:
        return BuildComparisonResult(
            status="NO_BASELINE",
            current_build_id=current_build_id,
            baseline_build_id=None,
            current_manifest=current_manifest,
            baseline_manifest=None,
        )

    try:
        previous = _load_manifest(
            baseline_path
        )
    except (
        OSError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        return BuildComparisonResult(
            status="FAILED",
            current_build_id=current_build_id,
            baseline_build_id=None,
            current_manifest=current_manifest,
            baseline_manifest=baseline_path,
            error=str(
                exc
            ),
        )

    metrics: list[
        ComparisonMetric
    ] = []

    for (
        code,
        label,
        path,
        format_kind,
    ) in _METRICS:
        current_value = _numeric_value(
            current,
            path,
        )
        previous_value = _numeric_value(
            previous,
            path,
        )

        metrics.append(
            _build_metric(
                code=code,
                label=label,
                current=current_value,
                previous=previous_value,
                format_kind=format_kind,
            )
        )

    return BuildComparisonResult(
        status="COMPARED",
        current_build_id=current_build_id,
        baseline_build_id=_build_id(
            previous
        ),
        current_manifest=current_manifest,
        baseline_manifest=baseline_path,
        metrics=tuple(
            metrics
        ),
    )


def _format_number(
    value: float,
    kind: str,
) -> str:
    if kind == "milliseconds":
        return (
            f"{value / 1000.0:.2f}s"
        )

    if kind == "score":
        return (
            f"{value:.0f}/100"
        )

    return (
        f"{int(round(value)):,}"
        .replace(
            ",",
            ".",
        )
    )


def _format_delta(
    metric: ComparisonMetric,
) -> str:
    if metric.trend == "UP":
        arrow = "↑"
    elif metric.trend == "DOWN":
        arrow = "↓"
    else:
        arrow = "="

    absolute = abs(
        metric.delta
    )

    if metric.format_kind == "milliseconds":
        absolute_text = (
            f"{absolute / 1000.0:.2f}s"
        )
    elif metric.format_kind == "score":
        absolute_text = (
            f"{absolute:.0f}"
        )
    else:
        absolute_text = (
            f"{int(round(absolute)):,}"
            .replace(
                ",",
                ".",
            )
        )

    if metric.delta_percent is None:
        return (
            f"{arrow} {absolute_text}"
        )

    if metric.trend == "SAME":
        return "="

    return (
        f"{arrow} {absolute_text}"
        f" ({abs(metric.delta_percent):.1f}%)"
    )


def format_comparison_summary(
    result: BuildComparisonResult,
) -> str:
    if result.status == "COMPARED":
        baseline = (
            result.baseline_build_id
            or "baseline"
        )

        return (
            "[bold green]COMPARED[/bold green]"
            f" · {len(result.metrics)} metrics"
            f" · baseline {baseline}"
        )

    if result.status == "NO_BASELINE":
        return (
            "[bold yellow]NO BASELINE[/bold yellow]"
            " · first comparable evidence."
        )

    return (
        "[bold red]FAILED[/bold red]"
        f" · {result.error or 'erro desconhecido'}"
    )


def build_comparison_panel(
    result: BuildComparisonResult,
) -> Panel:
    if result.status == "NO_BASELINE":
        body = Text(
            "No previous valid build manifest was found. "
            "This build becomes the baseline for the next comparison.",
        )

        return Panel(
            body,
            title=Text(
                "BUILD COMPARISON · NO BASELINE",
                style="bold yellow",
            ),
            border_style="yellow",
            padding=(1, 1),
        )

    if result.status == "FAILED":
        body = Text(
            result.error
            or "Comparison failed."
        )

        return Panel(
            body,
            title=Text(
                "BUILD COMPARISON · FAILED",
                style="bold red",
            ),
            border_style="red",
            padding=(1, 1),
        )

    table = Table(
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )

    table.add_column(
        "Metric",
        style="cyan",
        no_wrap=True,
    )

    table.add_column(
        "Previous",
        justify="right",
        no_wrap=True,
    )

    table.add_column(
        "Current",
        justify="right",
        no_wrap=True,
    )

    table.add_column(
        "Delta",
        justify="right",
        no_wrap=True,
    )

    for metric in result.metrics:
        table.add_row(
            metric.label,
            _format_number(
                metric.previous,
                metric.format_kind,
            ),
            _format_number(
                metric.current,
                metric.format_kind,
            ),
            _format_delta(
                metric
            ),
        )

    baseline = (
        result.baseline_build_id
        or "baseline"
    )

    current = (
        result.current_build_id
        or "current"
    )

    return Panel(
        table,
        title=Text(
            "BUILD COMPARISON",
            style="bold cyan",
        ),
        subtitle=(
            f"{baseline} → {current}"
        ),
        border_style="cyan",
        padding=(1, 1),
    )


def render_build_comparison(
    console: Console,
    result: BuildComparisonResult,
) -> None:
    console.print()
    console.print(
        build_comparison_panel(
            result
        )
    )