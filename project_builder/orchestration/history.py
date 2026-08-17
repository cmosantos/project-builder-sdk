from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


BUILD_HISTORY_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class BuildHistoryEntry:
    build_id: str
    generated_at: str
    stage: str
    qa_score: int
    runtime_quality: str
    health: str
    policy: str
    duration_seconds: float
    tokens: int
    requests: int
    repairs: int
    tests_passed: int
    warnings: int
    policy_violations: int


@dataclass(frozen=True)
class BuildHistoryResult:
    status: str
    path: Path
    total_builds: int
    entries: tuple[BuildHistoryEntry, ...] = ()
    skipped_manifests: int = 0
    error: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


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

    if text.endswith("Z"):
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


def _dict(
    value: object,
) -> dict[str, Any]:
    if isinstance(
        value,
        dict,
    ):
        return value

    return {}


def _int(
    value: object,
) -> int:
    if value is None:
        return 0

    if isinstance(
        value,
        bool,
    ):
        return int(
            value
        )

    try:
        return int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0


def _float(
    value: object,
) -> float:
    if value is None:
        return 0.0

    try:
        return float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0.0


def _text(
    value: object,
    *,
    default: str = "-",
) -> str:
    if value is None:
        return default

    text = str(
        value
    ).strip()

    return (
        text
        if text
        else default
    )


def _entry_from_manifest(
    manifest: dict[str, Any],
) -> BuildHistoryEntry:
    build = _dict(
        manifest.get(
            "build"
        )
    )

    qa = _dict(
        manifest.get(
            "qa"
        )
    )

    runtime = _dict(
        manifest.get(
            "runtime"
        )
    )

    runtime_quality = _dict(
        runtime.get(
            "quality"
        )
    )

    health = _dict(
        manifest.get(
            "health"
        )
    )

    policy = _dict(
        manifest.get(
            "policy"
        )
    )

    usage = _dict(
        manifest.get(
            "usage"
        )
    )

    usage_totals = _dict(
        usage.get(
            "totals"
        )
    )

    performance = _dict(
        manifest.get(
            "performance"
        )
    )

    build_id = _text(
        build.get(
            "build_id"
        ),
        default="",
    )

    generated_at = _text(
        manifest.get(
            "generated_at"
        ),
        default="",
    )

    if not build_id:
        raise ValueError(
            "Manifest sem build_id."
        )

    if _parse_timestamp(
        generated_at
    ) is None:
        raise ValueError(
            "Manifest sem generated_at válido."
        )

    return BuildHistoryEntry(
        build_id=build_id,
        generated_at=generated_at,
        stage=_text(
            build.get(
                "stage"
            )
        ).upper(),
        qa_score=_int(
            qa.get(
                "score"
            )
        ),
        runtime_quality=_text(
            runtime_quality.get(
                "status"
            )
        ),
        health=_text(
            health.get(
                "status"
            )
        ),
        policy=_text(
            policy.get(
                "status"
            )
        ),
        duration_seconds=round(
            _float(
                performance.get(
                    "total_duration_ms"
                )
            )
            / 1000.0,
            2,
        ),
        tokens=_int(
            usage_totals.get(
                "total_tokens"
            )
        ),
        requests=_int(
            usage_totals.get(
                "requests"
            )
        ),
        repairs=_int(
            build.get(
                "repairs"
            )
        ),
        tests_passed=_int(
            runtime_quality.get(
                "passed_count"
            )
        ),
        warnings=_int(
            runtime_quality.get(
                "warning_count"
            )
        ),
        policy_violations=_int(
            policy.get(
                "violation_count"
            )
        ),
    )


def collect_build_history(
    evidence_root: Path,
) -> tuple[
    tuple[BuildHistoryEntry, ...],
    int,
]:
    entries: list[
        BuildHistoryEntry
    ] = []

    skipped = 0

    for path in evidence_root.glob(
        "*/build_manifest.json"
    ):
        try:
            manifest = _load_manifest(
                path
            )

            entries.append(
                _entry_from_manifest(
                    manifest
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
            ValueError,
        ):
            skipped += 1

    entries.sort(
        key=lambda entry: (
            _parse_timestamp(
                entry.generated_at
            )
            or datetime.min.replace(
                tzinfo=timezone.utc
            )
        ),
        reverse=True,
    )

    return (
        tuple(
            entries
        ),
        skipped,
    )


def history_path_for(
    current_manifest: Path,
) -> Path:
    current_manifest = (
        current_manifest.resolve()
    )

    return (
        current_manifest
        .parent
        .parent
        / "build_history.json"
    )


def write_build_history_index(
    current_manifest: Path,
) -> BuildHistoryResult:
    path = history_path_for(
        current_manifest
    )

    evidence_root = (
        path.parent
    )

    try:
        entries, skipped = collect_build_history(
            evidence_root
        )

        payload = {
            "schema_version": (
                BUILD_HISTORY_SCHEMA_VERSION
            ),
            "generated_at": _utc_now_iso(),
            "total_builds": len(
                entries
            ),
            "skipped_manifests": skipped,
            "builds": [
                asdict(
                    entry
                )
                for entry in entries
            ],
        }

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temp_path = path.with_suffix(
            ".json.tmp"
        )

        temp_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        temp_path.replace(
            path
        )

        return BuildHistoryResult(
            status="INDEXED",
            path=path.resolve(),
            total_builds=len(
                entries
            ),
            entries=entries,
            skipped_manifests=skipped,
        )

    except Exception as exc:
        return BuildHistoryResult(
            status="FAILED",
            path=path.resolve(),
            total_builds=0,
            error=str(
                exc
            ),
        )


def _format_tokens(
    value: int,
) -> str:
    return (
        f"{value:,}"
        .replace(
            ",",
            ".",
        )
    )


def _short_build_id(
    build_id: str,
) -> str:
    if len(
        build_id
    ) <= 18:
        return build_id

    return (
        "..."
        + build_id[-12:]
    )


def format_history_summary(
    result: BuildHistoryResult,
) -> str:
    if result.status == "INDEXED":
        skipped = (
            f" · {result.skipped_manifests} skipped"
            if result.skipped_manifests
            else ""
        )

        return (
            "[bold green]INDEXED[/bold green]"
            f" · {result.total_builds} builds"
            f"{skipped}"
            f" · {result.path}"
        )

    return (
        "[bold red]FAILED[/bold red]"
        f" · {result.error or 'erro desconhecido'}"
    )


def build_history_panel(
    result: BuildHistoryResult,
    *,
    limit: int = 5,
) -> Panel:
    if result.status == "FAILED":
        return Panel(
            Text(
                result.error
                or "History index failed."
            ),
            title=Text(
                "BUILD HISTORY · FAILED",
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
        "Build",
        no_wrap=True,
    )
    table.add_column(
        "Stage",
        no_wrap=True,
    )
    table.add_column(
        "QA",
        justify="right",
        no_wrap=True,
    )
    table.add_column(
        "Runtime",
        no_wrap=True,
    )
    table.add_column(
        "Health",
        no_wrap=True,
    )
    table.add_column(
        "Policy",
        no_wrap=True,
    )
    table.add_column(
        "Time",
        justify="right",
        no_wrap=True,
    )
    table.add_column(
        "Tokens",
        justify="right",
        no_wrap=True,
    )
    table.add_column(
        "Repairs",
        justify="right",
        no_wrap=True,
    )

    for entry in result.entries[
        :max(
            0,
            limit,
        )
    ]:
        table.add_row(
            _short_build_id(
                entry.build_id
            ),
            entry.stage,
            str(
                entry.qa_score
            ),
            entry.runtime_quality,
            entry.health,
            entry.policy,
            f"{entry.duration_seconds:.2f}s",
            _format_tokens(
                entry.tokens
            ),
            str(
                entry.repairs
            ),
        )

    subtitle = (
        f"{result.total_builds} builds indexed"
    )

    if result.skipped_manifests:
        subtitle += (
            f" · {result.skipped_manifests} skipped"
        )

    return Panel(
        table,
        title=Text(
            "BUILD HISTORY",
            style="bold cyan",
        ),
        subtitle=subtitle,
        border_style="cyan",
        padding=(1, 1),
    )


def render_build_history(
    console: Console,
    result: BuildHistoryResult,
    *,
    limit: int = 5,
) -> None:
    console.print()
    console.print(
        build_history_panel(
            result,
            limit=limit,
        )
    )