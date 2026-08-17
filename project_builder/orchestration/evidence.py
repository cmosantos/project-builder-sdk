from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from project_builder.orchestration.health import (
    build_health_snapshot,
)
from project_builder.orchestration.performance import (
    build_performance_snapshot,
)
from project_builder.orchestration.policy import (
    DEFAULT_BUILD_POLICY,
    BuildPolicy,
    build_policy_snapshot,
)
from project_builder.orchestration.runtime_quality import (
    build_runtime_quality_snapshot,
)
from project_builder.orchestration.state import (
    ExecutionEvent,
    ProjectState,
)
from project_builder.orchestration.usage import (
    aggregate_agent_usage,
    usage_totals,
)


BUILD_EVIDENCE_SCHEMA_VERSION = "1.0"

DEFAULT_EVIDENCE_ROOT = (
    Path.cwd()
    / ".project_builder"
    / "evidence"
)


@dataclass(frozen=True)
class EvidenceWriteResult:
    status: str
    path: Path
    sha256: str | None = None
    size_bytes: int = 0
    error: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest()


def _json_safe(
    value: Any,
) -> Any:
    if value is None or isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if isinstance(
        value,
        datetime,
    ):
        return value.isoformat()

    if isinstance(
        value,
        Enum,
    ):
        return value.value

    if isinstance(
        value,
        Path,
    ):
        return str(
            value
        )

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key): _json_safe(
                item
            )
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            _json_safe(
                item
            )
            for item in value
        ]

    return str(
        value
    )


def _serialize_event(
    event: ExecutionEvent,
) -> dict[str, Any]:
    return {
        "sequence": event.sequence,
        "event_type": event.event_type,
        "stage": event.stage,
        "occurred_at": event.occurred_at.isoformat(),
        "elapsed_ms": round(
            float(
                event.elapsed_ms
            ),
            2,
        ),
        "source": event.source,
        "target": event.target,
        "details": _json_safe(
            event.details
        ),
    }


def _artifact_snapshot(
    workspace_root: Path,
    expected_files: Iterable[str],
) -> list[dict[str, Any]]:
    artifacts: list[
        dict[str, Any]
    ] = []

    for item in expected_files:
        relative_path = str(
            item
        )

        absolute_path = (
            workspace_root
            / relative_path
        )

        exists = (
            absolute_path.is_file()
        )

        artifacts.append(
            {
                "path": relative_path,
                "exists": exists,
                "size_bytes": (
                    absolute_path.stat().st_size
                    if exists
                    else 0
                ),
                "sha256": (
                    _sha256_file(
                        absolute_path
                    )
                    if exists
                    else None
                ),
            }
        )

    return artifacts


def _runtime_status(
    state: ProjectState,
) -> str | None:
    report = getattr(
        state.context,
        "runtime_report",
        None,
    )

    if report is None:
        return None

    return getattr(
        report,
        "status",
        None,
    )


def _qa_snapshot(
    state: ProjectState,
) -> dict[str, Any]:
    report = getattr(
        state.context,
        "qa_report",
        None,
    )

    if report is None:
        return {
            "status": None,
            "score": None,
        }

    return {
        "status": getattr(
            report,
            "status",
            None,
        ),
        "score": getattr(
            report,
            "score",
            None,
        ),
    }


def build_evidence_manifest(
    state: ProjectState,
    *,
    workspace_root: Path,
    expected_files: Iterable[str],
    sandbox_cleanup_ok: bool | None,
    policy: BuildPolicy = DEFAULT_BUILD_POLICY,
) -> dict[str, Any]:
    runtime_report = getattr(
        state.context,
        "runtime_report",
        None,
    )

    runtime_quality = (
        build_runtime_quality_snapshot(
            runtime_report
        )
    )

    health = build_health_snapshot(
        state,
        sandbox_cleanup_ok=sandbox_cleanup_ok,
    )

    policy_snapshot = build_policy_snapshot(
        state,
        policy=policy,
        sandbox_cleanup_ok=sandbox_cleanup_ok,
    )

    performance = build_performance_snapshot(
        state
    )

    totals = usage_totals(
        state
    )

    artifacts = _artifact_snapshot(
        workspace_root,
        expected_files,
    )

    artifact_count = len(
        artifacts
    )

    present_count = sum(
        artifact[
            "exists"
        ]
        for artifact in artifacts
    )

    return {
        "schema_version": (
            BUILD_EVIDENCE_SCHEMA_VERSION
        ),
        "generated_at": _utc_now_iso(),
        "build": {
            "build_id": state.build_id,
            "request": state.request,
            "stage": state.stage.value,
            "request_gate": {
                "status": (
                    state.request_gate_status
                ),
                "reason": (
                    state.request_gate_reason
                ),
            },
            "repairs": (
                state.repair_attempts
            ),
        },
        "qa": _qa_snapshot(
            state
        ),
        "runtime": {
            "status": _runtime_status(
                state
            ),
            "quality": runtime_quality,
            "history": _json_safe(
                state.runtime_history
            ),
        },
        "usage": {
            "totals": _json_safe(
                totals
            ),
            "agents": _json_safe(
                aggregate_agent_usage(
                    state
                )
            ),
        },
        "performance": _json_safe(
            performance
        ),
        "health": _json_safe(
            health
        ),
        "policy": _json_safe(
            policy_snapshot
        ),
        "flow": {
            "handoffs": list(
                state.handoff_history
            ),
            "transitions": list(
                state.transition_history
            ),
            "timeline": [
                _serialize_event(
                    event
                )
                for event
                in state.execution_events
            ],
        },
        "artifacts": {
            "workspace_root": str(
                workspace_root.resolve()
            ),
            "expected": artifact_count,
            "present": present_count,
            "files": artifacts,
        },
        "sandbox": {
            "mode": "SANDBOX_LOCAL",
            "cleanup_ok": (
                sandbox_cleanup_ok
            ),
        },
        "mcp": {
            "mode": "workspace-read-only",
        },
        "observability": {
            "langsmith": True,
            "trace_group_id": (
                state.build_id
            ),
        },
    }


def _validated_build_id(
    state: ProjectState,
) -> str:
    build_id = (
        state.build_id
        or ""
    ).strip()

    if not build_id:
        raise ValueError(
            "Build ID ausente; não é possível gerar evidência."
        )

    if not all(
        char.isalnum()
        or char in {
            "-",
            "_",
        }
        for char in build_id
    ):
        raise ValueError(
            "Build ID contém caracteres inválidos para o caminho de evidência."
        )

    return build_id


def evidence_path_for(
    state: ProjectState,
    *,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
) -> Path:
    build_id = _validated_build_id(
        state
    )

    return (
        evidence_root
        / build_id
        / "build_manifest.json"
    )


def write_build_manifest(
    state: ProjectState,
    *,
    workspace_root: Path,
    expected_files: Iterable[str],
    sandbox_cleanup_ok: bool | None,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    policy: BuildPolicy = DEFAULT_BUILD_POLICY,
) -> EvidenceWriteResult:
    path = evidence_path_for(
        state,
        evidence_root=evidence_root,
    )

    try:
        payload = build_evidence_manifest(
            state,
            workspace_root=workspace_root,
            expected_files=expected_files,
            sandbox_cleanup_ok=sandbox_cleanup_ok,
            policy=policy,
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temp_path = path.with_suffix(
            ".json.tmp"
        )

        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

        temp_path.write_text(
            serialized + "\n",
            encoding="utf-8",
        )

        temp_path.replace(
            path
        )

        return EvidenceWriteResult(
            status="WRITTEN",
            path=path.resolve(),
            sha256=_sha256_file(
                path
            ),
            size_bytes=path.stat().st_size,
        )

    except Exception as exc:
        return EvidenceWriteResult(
            status="FAILED",
            path=path.resolve(),
            error=str(
                exc
            ),
        )


def format_evidence_summary(
    result: EvidenceWriteResult,
) -> str:
    if result.status == "WRITTEN":
        return (
            "[bold green]WRITTEN[/bold green]"
            f" · {result.path}"
            f" · SHA-256 {result.sha256}"
        )

    return (
        "[bold red]FAILED[/bold red]"
        f" · {result.error or 'erro desconhecido'}"
    )


def render_build_evidence(
    console: Console,
    result: EvidenceWriteResult,
) -> None:
    table = Table.grid(
        padding=(0, 2)
    )

    table.add_column(
        style="bold cyan",
        no_wrap=True,
    )

    table.add_column()

    if result.status == "WRITTEN":
        table.add_row(
            "Status",
            "[bold green]WRITTEN[/bold green]",
        )
        table.add_row(
            "Manifest",
            str(
                result.path
            ),
        )
        table.add_row(
            "SHA-256",
            result.sha256 or "-",
        )
        table.add_row(
            "Size",
            f"{result.size_bytes} bytes",
        )

        border_style = "green"
        title_style = "bold green"

    else:
        table.add_row(
            "Status",
            "[bold red]FAILED[/bold red]",
        )
        table.add_row(
            "Manifest",
            str(
                result.path
            ),
        )
        table.add_row(
            "Error",
            result.error or "erro desconhecido",
        )

        border_style = "red"
        title_style = "bold red"

    console.print()

    console.print(
        Panel(
            table,
            title=Text(
                "BUILD EVIDENCE",
                style=title_style,
            ),
            border_style=border_style,
            padding=(1, 1),
        )
    )