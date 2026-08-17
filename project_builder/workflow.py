import asyncio
import hashlib
from uuid import uuid4

from agents import (
    Runner,
    custom_span,
    trace,
)

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

from project_builder.agents import (
    arquitetura_para_markdown,
    qa_agent,
    repair_agent,
    router_agent,
)
from project_builder.config import (
    EXPECTED_FILES,
    WORKSPACE_ROOT,
)
from project_builder.faults import aplicar_fault_injection
from project_builder.mcp.runtime import (
    read_workspace_snapshot_mcp,
)
from project_builder.models import (
    ProjectContext,
    QAReport,
    RuntimeReport,
)
from project_builder.observability import configure_observability
from project_builder.request_gate import (
    RequestGateResult,
    request_gate_agent,
)
from project_builder.orchestration.hooks import ProjectWorkflowHooks
from project_builder.orchestration.orchestrator import (
    ProjectOrchestrator,
)
from project_builder.orchestration.state import (
    ProjectStage,
    ProjectState,
)
from project_builder.orchestration.timeline import (
    render_execution_timeline,
)
from project_builder.orchestration.usage import (
    format_usage_summary,
    render_agent_usage,
    usage_totals,
)
from project_builder.orchestration.performance import (
    build_performance_snapshot,
    format_performance_summary,
    render_performance_summary,
)
from project_builder.orchestration.health import (
    build_health_snapshot,
    format_health_summary,
    render_build_health,
)
from project_builder.orchestration.policy import (
    build_policy_snapshot,
    format_policy_summary,
    render_build_policy,
)
from project_builder.orchestration.evidence import (
    EvidenceWriteResult,
    format_evidence_summary,
    render_build_evidence,
    write_build_manifest,
)
from project_builder.orchestration.comparison import (
    BuildComparisonResult,
    compare_with_previous_manifest,
    format_comparison_summary,
    render_build_comparison,
)
from project_builder.orchestration.history import (
    BuildHistoryResult,
    format_history_summary,
    render_build_history,
    write_build_history_index,
)
from project_builder.orchestration.runtime_quality import (
    build_runtime_quality_snapshot,
    format_runtime_history_summary,
    format_runtime_quality_summary,
    record_runtime_attempt,
    render_runtime_quality,
)
from project_builder.runtime import (
    SANDBOX_ROOT,
    executar_runtime_gate,
)
from project_builder.workspace import validar_arquivos_no_disco


# =========================================================
# CONFIGURAÇÃO DO WORKFLOW
# =========================================================

MAX_REPAIR_ATTEMPTS = 2


# =========================================================
# INTERFACE
# =========================================================

custom_theme = Theme(
    {
        "markdown.h1": "bold cyan not underline",
        "markdown.h1.border": "cyan",
        "markdown.h2": "bold cyan not underline",
        "markdown.h3": "bold bright_cyan not underline",
        "markdown.h4": "bold not underline",
        "markdown.h5": "bold not underline",
        "markdown.h6": "bold not underline",
    }
)

console = Console(theme=custom_theme)


# =========================================================
# FORMATAÇÃO DO QA
# =========================================================

def qa_para_markdown(
    relatorio: QAReport,
) -> str:
    verificacoes = (
        "\n".join(
            f"- {item}"
            for item in relatorio.verificacoes_aprovadas
        )
        or "- Nenhuma."
    )

    problemas = (
        "\n".join(
            f"- {item}"
            for item in relatorio.problemas_encontrados
        )
        or "- Nenhum problema relevante encontrado."
    )

    recomendacoes = (
        "\n".join(
            f"- {item}"
            for item in relatorio.recomendacoes
        )
        or "- Nenhuma recomendação adicional."
    )

    arquivos = (
        "\n".join(
            f"- {item}"
            for item in relatorio.arquivos_revisados
        )
        or "- Nenhum arquivo informado."
    )

    return f"""
**Status:** {relatorio.status}

**Score:** {relatorio.score}/100

**Resumo**

{relatorio.resumo}

**Verificações aprovadas**

{verificacoes}

**Problemas encontrados**

{problemas}

**Recomendações**

{recomendacoes}

**Arquivos revisados**

{arquivos}
""".strip()


# =========================================================
# RESUMO DO PYTEST
# =========================================================

def obter_resumo_pytest(
    relatorio: RuntimeReport,
) -> str:
    saida = (
        relatorio.pytest.stdout.strip()
        or relatorio.pytest.stderr.strip()
    )

    if not saida:
        return "Sem resultado informado."

    linhas = [
        linha.strip()
        for linha in saida.splitlines()
        if linha.strip()
    ]

    palavras_resultado = (
        "passed",
        "failed",
        "error",
        "errors",
        "skipped",
        "warning",
        "warnings",
    )

    for linha in reversed(linhas):
        linha_lower = linha.lower()

        if any(
            palavra in linha_lower
            for palavra in palavras_resultado
        ):
            if "http://" in linha_lower:
                continue

            if "https://" in linha_lower:
                continue

            if "docs:" in linha_lower:
                continue

            return linha

    return linhas[-1]


def obter_aviso_runtime(
    relatorio: RuntimeReport,
) -> str | None:
    saida = (
        relatorio.pytest.stdout
        + "\n"
        + relatorio.pytest.stderr
    )

    if (
        "PydanticDeprecatedSince20" in saida
        or "@validator" in saida
    ):
        return (
            "Pydantic: @validator está depreciado. "
            "Preferir @field_validator."
        )

    if "warning" in saida.lower():
        return (
            "O pytest registrou warning(s). "
            "Consulte a saída completa se necessário."
        )

    return None


# =========================================================
# SNAPSHOT DO WORKSPACE
# =========================================================

def snapshot_workspace() -> dict[str, str]:
    snapshot: dict[str, str] = {}

    for arquivo in EXPECTED_FILES:
        destino = WORKSPACE_ROOT / arquivo

        if not destino.exists():
            continue

        conteudo = destino.read_bytes()

        digest = hashlib.sha256(
            conteudo
        ).hexdigest()

        snapshot[arquivo] = digest

    return snapshot


def arquivos_alterados(
    antes: dict[str, str],
    depois: dict[str, str],
) -> list[str]:
    alterados: list[str] = []

    for arquivo in EXPECTED_FILES:
        if antes.get(arquivo) != depois.get(arquivo):
            alterados.append(
                arquivo
            )

    return alterados


# =========================================================
# VALIDAÇÃO DO DEVELOPER
# =========================================================

def validar_developer(
    resultado,
    contexto: ProjectContext,
) -> None:
    if resultado.last_agent.name != "Project Developer":
        raise RuntimeError(
            "Workflow agentic terminou "
            "no agente incorreto: "
            f"{resultado.last_agent.name}"
        )

    criados = set(
        contexto.created_files
    )

    esperados = set(
        EXPECTED_FILES
    )

    if criados != esperados:
        faltando = (
            esperados - criados
        )

        extras = (
            criados - esperados
        )

        detalhes: list[str] = []

        if faltando:
            detalhes.append(
                "faltando: "
                + ", ".join(
                    sorted(faltando)
                )
            )

        if extras:
            detalhes.append(
                "extras: "
                + ", ".join(
                    sorted(extras)
                )
            )

        raise RuntimeError(
            "Developer não entregou "
            "o contrato completo: "
            + " | ".join(detalhes)
        )

    ausentes = validar_arquivos_no_disco()

    if ausentes:
        raise RuntimeError(
            "Arquivos não encontrados fisicamente "
            "no workspace: "
            + ", ".join(ausentes)
        )


# =========================================================
# FAULT INJECTION
# =========================================================

def executar_fault_injection() -> None:
    resultado = aplicar_fault_injection()

    if resultado is None:
        return

    console.print()

    console.print(
        Panel(
            "[bold red]"
            "💣 FALHA CONTROLADA INJETADA"
            "[/bold red]\n\n"
            f"[yellow]{resultado}[/yellow]\n\n"
            "[dim]"
            "Modo exclusivo de teste do Repair Loop."
            "[/dim]",
            title=(
                "[bold red]"
                "FAULT INJECTION"
                "[/bold red]"
            ),
            border_style="red",
            padding=(1, 2),
        )
    )


def snapshot_mcp_para_texto(
    snapshot: dict,
) -> str:
    blocos: list[str] = []

    for item in snapshot.get("files", []):
        if not isinstance(item, dict):
            continue

        path = str(item.get("path", ""))
        content = str(item.get("content", ""))

        blocos.append(
            f"===== FILE: {path} =====\n"
            f"{content}\n"
            f"===== END FILE: {path} ====="
        )

    return "\n\n".join(blocos)


# =========================================================
# QA ESTÁTICO
# =========================================================

async def executar_qa(
    contexto: ProjectContext,
    hooks: ProjectWorkflowHooks,
) -> QAReport:
    console.print()

    console.print(
        Panel.fit(
            "[bold green]"
            "✓ Gate obrigatório"
            "[/bold green]\n"
            "[dim]"
            "Developer/Repair → QA"
            "[/dim]",
            border_style="green",
            padding=(1, 2),
        )
    )

    console.print()

    console.print(
        Panel(
            "[yellow]"
            "Auditando implementação..."
            "[/yellow]\n\n"
            "[dim]"
            "Project QA está revisando "
            "os arquivos reais do workspace."
            "[/dim]",
            title=(
                "[bold yellow]"
                "QA AGENT"
                "[/bold yellow]"
            ),
            border_style="yellow",
            padding=(1, 2),
        )
    )

    snapshot = await read_workspace_snapshot_mcp()
    snapshot_texto = snapshot_mcp_para_texto(
        snapshot
    )

    console.print(
        "  [green]✓[/green] MCP snapshot "
        f"{snapshot.get('file_count', '?')} arquivos · "
        f"{snapshot.get('total_bytes', '?')} bytes"
    )

    resultado = await Runner.run(
        qa_agent,
        (
            "Audite estaticamente o projeto atual "
            "conforme o ArchitecturePlan.\n\n"
            "SNAPSHOT MCP READ-ONLY\n\n"
            f"{snapshot_texto}"
        ),
        context=contexto,
        hooks=hooks,
        max_turns=3,
    )

    relatorio = resultado.final_output

    if not isinstance(
        relatorio,
        QAReport,
    ):
        raise RuntimeError(
            "QA Agent não retornou "
            "um QAReport válido."
        )

    contexto.qa_report = relatorio

    return relatorio


# =========================================================
# REPAIR
# =========================================================

async def executar_repair(
    contexto: ProjectContext,
    tentativa: int,
    origem: str,
    hooks: ProjectWorkflowHooks,
) -> list[str]:
    console.print()

    console.print(
        Panel.fit(
            "[bold yellow]"
            f"↻ Repair tentativa {tentativa}"
            f"/{MAX_REPAIR_ATTEMPTS}"
            "[/bold yellow]\n"
            "[dim]"
            f"Origem da falha: {origem}"
            "[/dim]",
            border_style="yellow",
            padding=(1, 2),
        )
    )

    console.print()

    console.print(
        Panel(
            "[yellow]"
            "Analisando falhas e corrigindo "
            "o projeto..."
            "[/yellow]\n\n"
            "[dim]"
            "Project Repair vai ler o workspace "
            "e alterar somente o necessário."
            "[/dim]",
            title=(
                "[bold yellow]"
                "REPAIR AGENT"
                "[/bold yellow]"
            ),
            border_style="yellow",
            padding=(1, 2),
        )
    )

    antes = snapshot_workspace()

    snapshot = await read_workspace_snapshot_mcp()
    snapshot_texto = snapshot_mcp_para_texto(
        snapshot
    )

    console.print(
        "  [green]✓[/green] MCP snapshot "
        f"{snapshot.get('file_count', '?')} arquivos · "
        f"{snapshot.get('total_bytes', '?')} bytes"
    )

    resultado = await Runner.run(
        repair_agent,
        (
            "Corrija os defeitos identificados "
            f"pelo {origem}. "
            "Preserve integralmente o "
            "ArchitecturePlan atual.\n\n"
            "SNAPSHOT MCP READ-ONLY\n\n"
            f"{snapshot_texto}"
        ),
        context=contexto,
        hooks=hooks,
        max_turns=5,
    )

    if resultado.last_agent.name != "Project Repair":
        raise RuntimeError(
            "Repair terminou no agente incorreto: "
            f"{resultado.last_agent.name}"
        )

    ausentes = validar_arquivos_no_disco()

    if ausentes:
        raise RuntimeError(
            "Repair deixou arquivos obrigatórios "
            "ausentes: "
            + ", ".join(ausentes)
        )

    depois = snapshot_workspace()

    alterados = arquivos_alterados(
        antes,
        depois,
    )

    if not alterados:
        raise RuntimeError(
            "Project Repair terminou sem alterar "
            "nenhum arquivo do workspace."
        )

    console.print()

    tabela = Table.grid(
        padding=(0, 2)
    )

    tabela.add_column(
        style="bold"
    )

    tabela.add_column()

    tabela.add_row(
        "Tentativa",
        f"{tentativa}/{MAX_REPAIR_ATTEMPTS}",
    )

    tabela.add_row(
        "Origem",
        origem,
    )

    tabela.add_row(
        "Arquivos",
        ", ".join(alterados),
    )

    console.print(
        Panel(
            tabela,
            title=(
                "[bold green]"
                "REPAIR APLICADO"
                "[/bold green]"
            ),
            border_style="green",
            padding=(1, 2),
        )
    )

    return alterados


# =========================================================
# RUNTIME GATE
# =========================================================

def executar_runtime(
    contexto: ProjectContext,
) -> RuntimeReport:
    console.print()

    console.print(
        Panel.fit(
            "[bold green]"
            "✓ Gate obrigatório"
            "[/bold green]\n"
            "[dim]"
            "QA → Runtime"
            "[/dim]",
            border_style="green",
            padding=(1, 2),
        )
    )

    console.print()

    console.print(
        Panel(
            "[yellow]"
            "Executando projeto..."
            "[/yellow]\n\n"
            "[dim]"
            "Smoke test + pytest + HTTP Live Check real "
            "usando o Python da aplicação."
            "[/dim]",
            title=(
                "[bold yellow]"
                "RUNTIME GATE"
                "[/bold yellow]"
            ),
            border_style="yellow",
            padding=(1, 2),
        )
    )

    with custom_span(
        "sandbox_runtime",
        {
            "sandbox_mode": "SANDBOX_LOCAL",
            "workspace_strategy": "temporary_copy",
        },
    ) as span:
        relatorio = executar_runtime_gate()

        span.span_data.data["output"] = {
            "status": relatorio.status,
            "smoke_test": relatorio.smoke_test.sucesso,
            "pytest": relatorio.pytest.sucesso,
            "http_live": (
                relatorio.http_check.sucesso
                if relatorio.http_check is not None
                else None
            ),
            "cleanup_ok": (
                not SANDBOX_ROOT.exists()
            ),
        }

    contexto.runtime_report = relatorio

    return relatorio


# =========================================================
# EXIBIÇÃO DA ARQUITETURA
# =========================================================

def exibir_arquitetura(
    contexto: ProjectContext,
) -> None:
    if contexto.architecture is None:
        return

    console.print()

    console.print(
        Panel(
            Markdown(
                arquitetura_para_markdown(
                    contexto.architecture
                )
            ),
            title=(
                "[bold cyan]"
                "PROJECT ARCHITECT"
                "[/bold cyan]"
            ),
            subtitle=(
                "[green]"
                "Arquitetura utilizada"
                "[/green]"
            ),
            border_style="cyan",
            padding=(1, 2),
        )
    )


# =========================================================
# EXIBIÇÃO DO QA
# =========================================================

def exibir_qa(
    relatorio: QAReport,
) -> None:
    cor = (
        "green"
        if relatorio.status == "APROVADO"
        else "red"
    )

    console.print()

    console.print(
        Panel(
            Markdown(
                qa_para_markdown(
                    relatorio
                )
            ),
            title=(
                f"[bold {cor}]"
                "PROJECT QA"
                f"[/bold {cor}]"
            ),
            subtitle=(
                f"[{cor}]"
                f"{relatorio.status}"
                f"[/{cor}]"
            ),
            border_style=cor,
            padding=(1, 2),
        )
    )


# =========================================================
# EXIBIÇÃO DO RUNTIME
# =========================================================

def exibir_runtime(
    relatorio: RuntimeReport,
) -> None:
    aprovado = (
        relatorio.status == "APROVADO"
    )

    cor = (
        "green"
        if aprovado
        else "red"
    )

    # =====================================================
    # STATUS DOS GATES
    # =====================================================

    smoke_status = (
        "[bold green]PASS[/bold green]"
        if relatorio.smoke_test.sucesso
        else "[bold red]FAIL[/bold red]"
    )

    if not relatorio.pytest.comando:
        pytest_status = "[yellow]SKIP[/yellow]"
    else:
        pytest_status = (
            "[bold green]PASS[/bold green]"
            if relatorio.pytest.sucesso
            else "[bold red]FAIL[/bold red]"
        )

    if relatorio.http_check is None:
        http_status = "[dim]N/A[/dim]"
    elif not relatorio.http_check.comando:
        http_status = "[yellow]SKIP[/yellow]"
    elif relatorio.http_check.sucesso:
        http_status = "[bold green]PASS[/bold green]"
    else:
        http_status = "[bold red]FAIL[/bold red]"

    # =====================================================
    # RESUMO DO PYTEST
    # =====================================================

    resumo_pytest = obter_resumo_pytest(
        relatorio
    )

    aviso = obter_aviso_runtime(
        relatorio
    )

    # =====================================================
    # DADOS DO HTTP LIVE CHECK
    # =====================================================

    http_url = "-"
    http_code = "-"
    openapi_version = "-"
    rotas = "-"

    if (
        relatorio.http_check is not None
        and relatorio.http_check.stdout
    ):
        for linha in (
            relatorio.http_check.stdout.splitlines()
        ):
            linha = linha.strip()

            if linha.startswith("URL:"):
                http_url = linha.removeprefix(
                    "URL:"
                ).strip()

            elif linha.startswith("Status HTTP:"):
                http_code = linha.removeprefix(
                    "Status HTTP:"
                ).strip()

            elif linha.startswith("OpenAPI:"):
                openapi_version = linha.removeprefix(
                    "OpenAPI:"
                ).strip()

            elif linha.startswith("Rotas detectadas:"):
                rotas = linha.removeprefix(
                    "Rotas detectadas:"
                ).strip()

    # =====================================================
    # TABELA PRINCIPAL
    # =====================================================

    tabela = Table.grid(
        padding=(0, 2)
    )

    tabela.add_column(
        style="bold",
        no_wrap=True,
    )

    tabela.add_column()

    tabela.add_row(
        "Status",
        (
            "[bold green]APROVADO[/bold green]"
            if aprovado
            else "[bold red]REPROVADO[/bold red]"
        ),
    )

    tabela.add_row(
        "Python",
        relatorio.python_executable,
    )

    tabela.add_row(
        "Smoke test",
        smoke_status,
    )

    tabela.add_row(
        "Pytest",
        pytest_status,
    )

    tabela.add_row(
        "HTTP Live",
        http_status,
    )

    tabela.add_row(
        "Resultado",
        resumo_pytest,
    )

    # =====================================================
    # DETALHES DO HTTP
    # =====================================================

    if (
        relatorio.http_check is not None
        and relatorio.http_check.sucesso
    ):
        tabela.add_row(
            "HTTP Status",
            http_code,
        )

        tabela.add_row(
            "OpenAPI",
            openapi_version,
        )

        tabela.add_row(
            "Rotas",
            rotas,
        )

        tabela.add_row(
            "URL",
            http_url,
        )

    # =====================================================
    # DIAGNÓSTICO DE FALHAS
    # =====================================================

    if not relatorio.smoke_test.sucesso:
        detalhe = (
            relatorio.smoke_test.stderr.strip()
            or relatorio.smoke_test.stdout.strip()
            or (
                "Smoke test terminou com código "
                f"{relatorio.smoke_test.return_code}."
            )
        )

        linhas = [
            linha.rstrip()
            for linha in detalhe.splitlines()
            if linha.strip()
        ]

        detalhe_curto = "\n".join(
            linhas[-8:]
        )

        detalhe_curto = detalhe_curto.replace(
            "[",
            "\\[",
        )

        tabela.add_row(
            "Erro smoke",
            f"[red]{detalhe_curto}[/red]",
        )

    elif (
        relatorio.pytest.comando
        and not relatorio.pytest.sucesso
    ):
        detalhe = (
            relatorio.pytest.stderr.strip()
            or relatorio.pytest.stdout.strip()
            or (
                "Pytest terminou com código "
                f"{relatorio.pytest.return_code}."
            )
        )

        linhas = [
            linha.rstrip()
            for linha in detalhe.splitlines()
            if linha.strip()
        ]

        detalhe_curto = "\n".join(
            linhas[-10:]
        )

        detalhe_curto = detalhe_curto.replace(
            "[",
            "\\[",
        )

        tabela.add_row(
            "Erro pytest",
            f"[red]{detalhe_curto}[/red]",
        )

    elif (
        relatorio.http_check is not None
        and relatorio.http_check.comando
        and not relatorio.http_check.sucesso
    ):
        detalhe = (
            relatorio.http_check.stderr.strip()
            or relatorio.http_check.stdout.strip()
            or (
                "HTTP Live Check terminou com código "
                f"{relatorio.http_check.return_code}."
            )
        )

        linhas = [
            linha.rstrip()
            for linha in detalhe.splitlines()
            if linha.strip()
        ]

        detalhe_curto = "\n".join(
            linhas[-10:]
        )

        detalhe_curto = detalhe_curto.replace(
            "[",
            "\\[",
        )

        tabela.add_row(
            "Erro HTTP",
            f"[red]{detalhe_curto}[/red]",
        )

    # =====================================================
    # WARNINGS
    # =====================================================

    if aviso:
        tabela.add_row(
            "Aviso",
            f"[yellow]⚠ {aviso}[/yellow]",
        )

    # =====================================================
    # PAINEL
    # =====================================================

    console.print()

    console.print(
        Panel(
            tabela,
            title=(
                f"[bold {cor}]"
                "RUNTIME REPORT"
                f"[/bold {cor}]"
            ),
            subtitle=(
                f"[{cor}]"
                f"{relatorio.status}"
                f"[/{cor}]"
            ),
            border_style=cor,
            padding=(1, 2),
        )
    )

    render_runtime_quality(
        console,
        relatorio,
    )


# =========================================================
# EXIBIÇÃO DO WORKSPACE
# =========================================================

def exibir_workspace() -> None:
    console.print()

    console.print(
        "[bold cyan]"
        "Workspace final:"
        "[/bold cyan]"
    )

    for arquivo in EXPECTED_FILES:
        destino = (
            WORKSPACE_ROOT / arquivo
        )

        if destino.exists():
            console.print(
                f"  [green]✓[/green] "
                f"{arquivo}"
            )
        else:
            console.print(
                f"  [red]✗[/red] "
                f"{arquivo}"
            )

    console.print()

    console.print(
        f"[dim]"
        f"{WORKSPACE_ROOT}"
        f"[/dim]"
    )

    console.print()


# =========================================================
# RESULTADO FINAL
# =========================================================

def montar_fluxo_executado(
    state: ProjectState,
) -> str:
    etapas = [
        "Request Gate",
        "Router",
        "Architect",
        "Developer",
    ]

    for transicao in state.transition_history:
        if transicao == "development -> qa":
            etapas.append("QA")
        elif transicao == "qa -> repair":
            etapas.append("Repair")
        elif transicao == "repair -> qa":
            etapas.append("QA")
        elif transicao == "qa -> runtime":
            etapas.append("Runtime")
        elif transicao == "runtime -> repair":
            etapas.append("Repair")

    return " → ".join(etapas)


def formatar_handoffs(
    state: ProjectState,
) -> str:
    if not state.handoff_history:
        return "[dim]Nenhum handoff registrado.[/dim]"

    return "\n".join(
        f"[green]✓[/green] {handoff}"
        for handoff in state.handoff_history
    )


def formatar_transicoes(
    state: ProjectState,
) -> str:
    transicoes = [
        item
        for item in state.transition_history
        if " -> " in item
    ]

    if not transicoes:
        return "[dim]Nenhuma transição registrada.[/dim]"

    return "\n".join(
        f"[cyan]•[/cyan] {item.replace(' -> ', ' → ')}"
        for item in transicoes
    )


def formatar_runtime(
    state: ProjectState,
) -> str:
    relatorio = state.context.runtime_report

    if relatorio is None:
        return "[dim]Runtime não executado.[/dim]"

    smoke = (
        "[green]PASS[/green]"
        if relatorio.smoke_test.sucesso
        else "[red]FAIL[/red]"
    )

    if not relatorio.pytest.comando:
        pytest_status = "[yellow]SKIP[/yellow]"
    else:
        pytest_status = (
            "[green]PASS[/green]"
            if relatorio.pytest.sucesso
            else "[red]FAIL[/red]"
        )

    if relatorio.http_check is None:
        http_status = "[dim]N/A[/dim]"
    elif not relatorio.http_check.comando:
        http_status = "[yellow]SKIP[/yellow]"
    else:
        http_status = (
            "[green]PASS[/green]"
            if relatorio.http_check.sucesso
            else "[red]FAIL[/red]"
        )

    return (
        f"Smoke {smoke}  |  "
        f"Pytest {pytest_status}  |  "
        f"HTTP {http_status}"
    )


def formatar_workspace() -> str:
    presentes = [
        arquivo
        for arquivo in EXPECTED_FILES
        if (WORKSPACE_ROOT / arquivo).exists()
    ]

    linhas = [
        f"[green]✓[/green] {arquivo}"
        for arquivo in presentes
    ]

    ausentes = [
        arquivo
        for arquivo in EXPECTED_FILES
        if not (WORKSPACE_ROOT / arquivo).exists()
    ]

    linhas.extend(
        f"[red]✗[/red] {arquivo}"
        for arquivo in ausentes
    )

    return "\n".join(linhas)



def formatar_mcp() -> str:
    return (
        "[green]Workspace MCP · READ-ONLY · deterministic[/green]"
    )


def formatar_observability() -> str:
    return (
        "[green]LangSmith · TRACE E2E[/green]"
    )


def formatar_sandbox(
    state: ProjectState,
) -> str:
    relatorio = state.context.runtime_report

    if relatorio is None:
        return "[dim]Não executado[/dim]"

    status = (
        "[green]PASS[/green]"
        if relatorio.status == "APROVADO"
        else "[red]FAIL[/red]"
    )

    cleanup = (
        "[green]cleanup OK[/green]"
        if not SANDBOX_ROOT.exists()
        else "[red]cleanup pendente[/red]"
    )

    return (
        f"SANDBOX_LOCAL · {status} · {cleanup}"
    )


def montar_trace_metadata(
    state: ProjectState,
) -> dict[str, object]:
    qa_report = state.context.qa_report
    runtime_report = state.context.runtime_report
    runtime_quality = (
        build_runtime_quality_snapshot(
            runtime_report
        )
        if runtime_report is not None
        else None
    )
    llm_usage = usage_totals(
        state
    )
    performance = build_performance_snapshot(
        state
    )
    health = build_health_snapshot(
        state,
        sandbox_cleanup_ok=(
            not SANDBOX_ROOT.exists()
        ),
    )
    policy = build_policy_snapshot(
        state,
        sandbox_cleanup_ok=(
            not SANDBOX_ROOT.exists()
        ),
    )

    return {
        "build_id": state.build_id,
        "request_gate_status": state.request_gate_status,
        "request_gate_reason": state.request_gate_reason,
        "final_stage": state.stage.value,
        "current_agent": state.current_agent,
        "previous_agent": state.previous_agent,
        "repair_attempts": state.repair_attempts,
        "handoff_count": len(
            state.handoff_history
        ),
        "handoffs": list(
            state.handoff_history
        ),
        "transitions": list(
            state.transition_history
        ),
        "execution_event_count": len(
            state.execution_events
        ),
        "execution_events": [
            {
                "sequence": event.sequence,
                "event_type": event.event_type,
                "stage": event.stage,
                "occurred_at": event.occurred_at.isoformat(),
                "elapsed_ms": event.elapsed_ms,
                "source": event.source,
                "target": event.target,
                "details": dict(event.details),
            }
            for event in state.execution_events
        ],
        "agent_usage_count": len(
            state.agent_usage
        ),
        "agent_usage": [
            {
                "sequence": metric.sequence,
                "agent_name": metric.agent_name,
                "stage": metric.stage,
                "requests": metric.requests,
                "input_tokens": metric.input_tokens,
                "output_tokens": metric.output_tokens,
                "total_tokens": metric.total_tokens,
                "cached_tokens": metric.cached_tokens,
                "reasoning_tokens": metric.reasoning_tokens,
            }
            for metric in state.agent_usage
        ],
        "llm_requests": llm_usage[
            "requests"
        ],
        "llm_input_tokens": llm_usage[
            "input_tokens"
        ],
        "llm_output_tokens": llm_usage[
            "output_tokens"
        ],
        "llm_total_tokens": llm_usage[
            "total_tokens"
        ],
        "llm_cached_tokens": llm_usage[
            "cached_tokens"
        ],
        "llm_reasoning_tokens": llm_usage[
            "reasoning_tokens"
        ],
        "performance_total_duration_ms": performance[
            "total_duration_ms"
        ],
        "performance_agent_duration_ms": performance[
            "agent_duration_ms"
        ],
        "performance_non_agent_duration_ms": performance[
            "non_agent_duration_ms"
        ],
        "performance_slowest_agent": performance[
            "slowest_agent"
        ],
        "performance_slowest_agent_ms": performance[
            "slowest_agent_ms"
        ],
        "performance_highest_usage_agent": performance[
            "highest_usage_agent"
        ],
        "performance_highest_usage_tokens": performance[
            "highest_usage_tokens"
        ],
        "performance_most_requests_agent": performance[
            "most_requests_agent"
        ],
        "performance_most_requests": performance[
            "most_requests"
        ],
        "agent_performance": performance[
            "agents"
        ],
        "health_status": health[
            "status"
        ],
        "health_pass_count": health[
            "pass_count"
        ],
        "health_warn_count": health[
            "warn_count"
        ],
        "health_fail_count": health[
            "fail_count"
        ],
        "health_findings": health[
            "findings"
        ],
        "policy_status": policy[
            "status"
        ],
        "policy_pass_count": policy[
            "pass_count"
        ],
        "policy_violation_count": policy[
            "violation_count"
        ],
        "policy_config": policy[
            "policy"
        ],
        "policy_checks": policy[
            "checks"
        ],
        "qa_status": (
            qa_report.status
            if qa_report is not None
            else None
        ),
        "qa_score": (
            qa_report.score
            if qa_report is not None
            else None
        ),
        "runtime_status": (
            runtime_report.status
            if runtime_report is not None
            else None
        ),
        "runtime_quality_status": (
            runtime_quality[
                "status"
            ]
            if runtime_quality is not None
            else None
        ),
        "runtime_pytest_passed": (
            runtime_quality[
                "passed_count"
            ]
            if runtime_quality is not None
            else 0
        ),
        "runtime_pytest_failed": (
            runtime_quality[
                "failed_count"
            ]
            if runtime_quality is not None
            else 0
        ),
        "runtime_pytest_errors": (
            runtime_quality[
                "error_count"
            ]
            if runtime_quality is not None
            else 0
        ),
        "runtime_pytest_warnings": (
            runtime_quality[
                "warning_count"
            ]
            if runtime_quality is not None
            else 0
        ),
        "runtime_pytest_warning_detected": (
            runtime_quality[
                "warning_detected"
            ]
            if runtime_quality is not None
            else False
        ),
        "runtime_attempt_count": len(
            state.runtime_history
        ),
        "runtime_history": [
            dict(
                attempt
            )
            for attempt in state.runtime_history
        ],
        "runtime_pytest_skipped": (
            runtime_quality[
                "skipped_count"
            ]
            if runtime_quality is not None
            else 0
        ),
        "sandbox_mode": "SANDBOX_LOCAL",
        "sandbox_cleanup_ok": (
            not SANDBOX_ROOT.exists()
        ),
        "mcp_mode": "workspace-read-only",
    }

def exibir_resultado_final(
    state: ProjectState,
    aprovado: bool,
    evidence: EvidenceWriteResult,
    comparison: BuildComparisonResult,
    history: BuildHistoryResult,
) -> None:
    cor = (
        "green"
        if aprovado
        else "red"
    )

    status = (
        "[bold green]✓ APROVADO[/bold green]"
        if aprovado
        else "[bold red]✗ REPROVADO[/bold red]"
    )

    qa_report = state.context.qa_report

    if qa_report is None:
        qa_status = "[dim]Não executado[/dim]"
    else:
        qa_cor = (
            "green"
            if qa_report.status == "APROVADO"
            else "red"
        )
        qa_status = (
            f"[{qa_cor}]"
            f"{qa_report.status} · {qa_report.score}/100"
            f"[/{qa_cor}]"
        )

    fluxo = montar_fluxo_executado(
        state
    )

    handoffs = formatar_handoffs(
        state
    )

    transicoes = formatar_transicoes(
        state
    )

    runtime = formatar_runtime(
        state
    )

    workspace = formatar_workspace()

    arquivos_presentes = sum(
        1
        for arquivo in EXPECTED_FILES
        if (WORKSPACE_ROOT / arquivo).exists()
    )

    tabela = Table.grid(
        padding=(0, 2)
    )

    tabela.add_column(
        style="bold",
        no_wrap=True,
    )
    tabela.add_column()

    tabela.add_row(
        "Status",
        status,
    )
    tabela.add_row(
        "Stage",
        f"[bold]{state.stage.value.upper()}[/bold]",
    )
    tabela.add_row(
        "Build ID",
        state.build_id or "-",
    )
    tabela.add_row(
        "Agente ativo",
        "[dim]nenhum — execução encerrada[/dim]",
    )
    tabela.add_row(
        "QA",
        qa_status,
    )
    tabela.add_row(
        "Reparos",
        (
            f"{state.repair_attempts}"
            f"/{MAX_REPAIR_ATTEMPTS}"
        ),
    )
    tabela.add_row(
        "Workspace",
        (
            f"{arquivos_presentes}"
            f"/{len(EXPECTED_FILES)} arquivos"
        ),
    )

    tabela.add_row(
        "",
        "",
    )
    tabela.add_row(
        "[bold cyan]FLUXO EXECUTADO[/bold cyan]",
        fluxo,
    )

    tabela.add_row(
        "",
        "",
    )
    tabela.add_row(
        "[bold cyan]HANDOFFS REAIS[/bold cyan]",
        handoffs,
    )

    tabela.add_row(
        "",
        "",
    )
    tabela.add_row(
        "[bold cyan]RUNTIME[/bold cyan]",
        runtime,
    )
    tabela.add_row(
        "[bold cyan]RUNTIME QUALITY[/bold cyan]",
        (
            format_runtime_quality_summary(
                state.context.runtime_report
            )
            if state.context.runtime_report is not None
            else "[dim]Não executado.[/dim]"
        ),
    )
    tabela.add_row(
        "[bold cyan]RUNTIME HISTORY[/bold cyan]",
        format_runtime_history_summary(
            state
        ),
    )
    tabela.add_row(
        "[bold cyan]MCP[/bold cyan]",
        formatar_mcp(),
    )
    tabela.add_row(
        "[bold cyan]SANDBOX[/bold cyan]",
        formatar_sandbox(
            state
        ),
    )
    tabela.add_row(
        "[bold cyan]OBSERVABILITY[/bold cyan]",
        formatar_observability(),
    )
    tabela.add_row(
        "[bold cyan]LLM USAGE[/bold cyan]",
        format_usage_summary(
            state
        ),
    )
    tabela.add_row(
        "[bold cyan]PERFORMANCE[/bold cyan]",
        format_performance_summary(
            state
        ),
    )
    tabela.add_row(
        "[bold cyan]HEALTH[/bold cyan]",
        format_health_summary(
            state,
            sandbox_cleanup_ok=(
                not SANDBOX_ROOT.exists()
            ),
        ),
    )
    tabela.add_row(
        "[bold cyan]POLICY[/bold cyan]",
        format_policy_summary(
            state,
            sandbox_cleanup_ok=(
                not SANDBOX_ROOT.exists()
            ),
        ),
    )
    tabela.add_row(
        "[bold cyan]EVIDENCE[/bold cyan]",
        format_evidence_summary(
            evidence
        ),
    )
    tabela.add_row(
        "[bold cyan]COMPARISON[/bold cyan]",
        format_comparison_summary(
            comparison
        ),
    )
    tabela.add_row(
        "[bold cyan]HISTORY[/bold cyan]",
        format_history_summary(
            history
        ),
    )

    tabela.add_row(
        "",
        "",
    )
    tabela.add_row(
        "[bold cyan]TRANSIÇÕES[/bold cyan]",
        transicoes,
    )

    tabela.add_row(
        "",
        "",
    )
    tabela.add_row(
        "[bold cyan]ARQUIVOS[/bold cyan]",
        workspace,
    )

    console.print()

    console.print(
        Panel(
            tabela,
            title=(
                f"[bold {cor}]"
                "PROJECT BUILD SUMMARY"
                f"[/bold {cor}]"
            ),
            subtitle=(
                f"[{cor}]"
                f"{state.stage.value.upper()}"
                f"[/{cor}]"
            ),
            border_style=cor,
            padding=(1, 2),
        )
    )

    console.print()

    console.print(
        f"[dim]Workspace: {WORKSPACE_ROOT}[/dim]"
    )

    console.print()


# =========================================================
# REQUEST GATE
# =========================================================

def exibir_request_gate(
    state: ProjectState,
    resultado: RequestGateResult,
) -> None:
    if resultado.status == "IMPLEMENTABLE":
        cor = "green"
        titulo = "✓ REQUEST GATE · IMPLEMENTABLE"
    elif resultado.status == "NEEDS_INPUT":
        cor = "yellow"
        titulo = "REQUEST GATE · NEEDS_INPUT"
    else:
        cor = "red"
        titulo = "REQUEST GATE · UNSUPPORTED"

    linhas: list[str] = [
        f"[bold]Status[/bold]  {resultado.status}",
        f"[bold]Motivo[/bold]  {resultado.reason}",
    ]

    if resultado.unsupported_requirements:
        linhas.append(
            "[bold]Não suportado[/bold]  "
            + ", ".join(
                resultado.unsupported_requirements
            )
        )

    if resultado.missing_information:
        linhas.append(
            "[bold]Falta informar[/bold]  "
            + ", ".join(
                resultado.missing_information
            )
        )

    if resultado.status != "IMPLEMENTABLE":
        linhas.extend(
            [
                "[bold]Developer[/bold]  NÃO EXECUTADO",
                "[bold]QA[/bold]         NÃO EXECUTADO",
                "[bold]Runtime[/bold]    NÃO EXECUTADO",
                "[bold]Workspace[/bold]  NÃO ALTERADO",
                f"[bold]Build ID[/bold]   {state.build_id or '-'}",
            ]
        )

    console.print()
    console.print(
        Panel(
            "\n".join(linhas),
            title=f"[bold {cor}]{titulo}[/bold {cor}]",
            border_style=cor,
            padding=(1, 2),
        )
    )


def finalizar_request_gate(
    state: ProjectState,
    orchestrator: ProjectOrchestrator,
    resultado: RequestGateResult,
) -> ProjectState:
    if resultado.status == "NEEDS_INPUT":
        final_stage = ProjectStage.NEEDS_INPUT
    elif resultado.status == "UNSUPPORTED":
        final_stage = ProjectStage.UNSUPPORTED
    else:
        raise RuntimeError(
            "finalizar_request_gate recebeu status implementável."
        )

    orchestrator.transition(
        state,
        final_stage,
    )
    orchestrator.clear_agent(
        state
    )

    render_execution_timeline(
        console,
        state,
    )

    render_agent_usage(
        console,
        state,
    )

    render_performance_summary(
        console,
        state,
    )

    exibir_request_gate(
        state,
        resultado,
    )

    return state


# =========================================================
# FINALIZAÇÃO DA EXECUÇÃO
# =========================================================

def finalizar_execucao(
    state: ProjectState,
    orchestrator: ProjectOrchestrator,
    aprovado: bool,
) -> ProjectState:
    final_stage = (
        ProjectStage.COMPLETED
        if aprovado
        else ProjectStage.FAILED
    )

    orchestrator.transition(
        state,
        final_stage,
    )

    if state.current_agent is not None:
        orchestrator.clear_agent(
            state
        )

    render_execution_timeline(
        console,
        state,
    )

    render_agent_usage(
        console,
        state,
    )

    render_performance_summary(
        console,
        state,
    )

    render_build_health(
        console,
        state,
        sandbox_cleanup_ok=(
            not SANDBOX_ROOT.exists()
        ),
    )

    render_build_policy(
        console,
        state,
        sandbox_cleanup_ok=(
            not SANDBOX_ROOT.exists()
        ),
    )

    evidence = write_build_manifest(
        state,
        workspace_root=WORKSPACE_ROOT,
        expected_files=EXPECTED_FILES,
        sandbox_cleanup_ok=(
            not SANDBOX_ROOT.exists()
        ),
    )

    render_build_evidence(
        console,
        evidence,
    )

    comparison = compare_with_previous_manifest(
        evidence.path
    )

    render_build_comparison(
        console,
        comparison,
    )

    history = write_build_history_index(
        evidence.path
    )

    render_build_history(
        console,
        history,
    )

    exibir_resultado_final(
        state=state,
        aprovado=aprovado,
        evidence=evidence,
        comparison=comparison,
        history=history,
    )

    return state


# =========================================================
# WORKFLOW PRINCIPAL
# =========================================================

async def run_project_async(
    pedido: str,
) -> ProjectState:
    if not pedido.strip():
        raise ValueError(
            "O pedido não pode estar vazio."
        )

    configure_observability()

    state = ProjectState(
        request=pedido,
    )
    orchestrator = ProjectOrchestrator()
    hooks = ProjectWorkflowHooks(
        state=state,
        orchestrator=orchestrator,
    )
    contexto = state.context

    build_id = (
        "project-builder-"
        + uuid4().hex
    )
    state.build_id = build_id

    project_trace = trace(
        "Project Builder",
        group_id=build_id,
        metadata={
            "build_id": build_id,
            "runtime": "openai-agents-sdk",
            "mcp_mode": "workspace-read-only",
            "sandbox_mode": "SANDBOX_LOCAL",
        },
    )
    project_trace.start(
        mark_as_current=True
    )

    console.print()

    console.print(
        Panel.fit(
            "[bold cyan]"
            "PROJECT BUILDER SDK"
            "[/bold cyan]\n"
            "[dim]"
            "Request Gate → Router → Architect → Developer "
            "→ QA → Repair → Runtime\n"
            "[dim]MCP · SANDBOX_LOCAL · LangSmith[/dim]"
            "[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
    )

    try:
        # =================================================
        # FASE 0
        # REQUEST GATE
        # =================================================

        orchestrator.transition(
            state,
            ProjectStage.REQUEST_VALIDATION,
        )

        console.print()
        console.print(
            Panel(
                "[yellow]"
                "Validando se o pedido cabe no perfil atual..."
                "[/yellow]\n\n"
                "[dim]"
                "O gate não constrói nada. "
                "Ele decide se o pedido pode seguir."
                "[/dim]",
                title=(
                    "[bold yellow]"
                    "REQUEST GATE"
                    "[/bold yellow]"
                ),
                border_style="yellow",
                padding=(1, 2),
            )
        )

        resultado_gate_run = await Runner.run(
            request_gate_agent,
            pedido,
            context=contexto,
            hooks=hooks,
            max_turns=3,
        )

        resultado_gate = resultado_gate_run.final_output

        if not isinstance(
            resultado_gate,
            RequestGateResult,
        ):
            raise RuntimeError(
                "Request Gate não retornou "
                "RequestGateResult válido."
            )

        state.request_gate_status = resultado_gate.status
        state.request_gate_reason = resultado_gate.reason

        if resultado_gate.status != "IMPLEMENTABLE":
            return finalizar_request_gate(
                state,
                orchestrator,
                resultado_gate,
            )

        exibir_request_gate(
            state,
            resultado_gate,
        )

        # =================================================
        # FASE 1
        # ROUTER → ARCHITECT → DEVELOPER
        # =================================================

        orchestrator.transition(
            state,
            ProjectStage.ROUTING,
        )
        console.print()

        console.print(
            Panel(
                "[yellow]"
                "Analisando solicitação..."
                "[/yellow]\n\n"
                "[dim]"
                "Project Router iniciou "
                "o workflow."
                "[/dim]",
                title=(
                    "[bold yellow]"
                    "ROUTER AGENT"
                    "[/bold yellow]"
                ),
                border_style="yellow",
                padding=(1, 2),
            )
        )

        resultado_dev = await Runner.run(
            router_agent,
            pedido,
            context=contexto,
            hooks=hooks,
            max_turns=10,
        )

        validar_developer(
            resultado_dev,
            contexto,
        )

        orchestrator.transition(
            state,
            ProjectStage.DEVELOPMENT,
        )
        console.print()

        console.print(
            Panel.fit(
                "[bold green]"
                "✓ Implementação criada"
                "[/bold green]\n"
                "[dim]"
                "Router → Architect → Developer"
                "[/dim]",
                border_style="green",
                padding=(1, 2),
            )
        )

        exibir_arquitetura(
            contexto
        )

        # =================================================
        # FASE DE TESTE CONTROLADO
        # FAULT INJECTION É OPCIONAL
        # =================================================

        executar_fault_injection()

        # =================================================
        # FASE 2
        # QA INICIAL
        # =================================================

        orchestrator.transition(
            state,
            ProjectStage.QA,
        )
        orchestrator.activate_agent(
            state,
            "Project QA",
        )

        qa_report = await executar_qa(
            contexto,
            hooks,
        )

        exibir_qa(
            qa_report
        )

        # =================================================
        # LOOP CONTROLADO
        # =================================================

        while True:
            # ---------------------------------------------
            # QA REPROVADO
            # ---------------------------------------------

            if qa_report.status != "APROVADO":
                if (
                    state.repair_attempts
                    >= MAX_REPAIR_ATTEMPTS
                ):
                    return finalizar_execucao(
                        state,
                        orchestrator,
                        aprovado=False,
                    )

                orchestrator.begin_repair(
                    state,
                    origin="QA",
                )

                await executar_repair(
                    contexto,
                    tentativa=state.repair_attempts,
                    origem="QA",
                    hooks=hooks,
                )

                contexto.runtime_report = None

                orchestrator.transition(
                    state,
                    ProjectStage.QA,
                )
                orchestrator.activate_agent(
                    state,
                    "Project QA",
                )

                qa_report = await executar_qa(
                    contexto,
                    hooks,
                )

                exibir_qa(
                    qa_report
                )

                continue

            # ---------------------------------------------
            # QA APROVADO → RUNTIME
            # ---------------------------------------------

            orchestrator.transition(
                state,
                ProjectStage.RUNTIME,
            )
            orchestrator.clear_agent(state)

            runtime_report = executar_runtime(
                contexto
            )

            record_runtime_attempt(
                state,
                runtime_report,
            )

            exibir_runtime(
                runtime_report
            )

            # ---------------------------------------------
            # RUNTIME APROVADO
            # ---------------------------------------------

            if runtime_report.status == "APROVADO":
                return finalizar_execucao(
                    state,
                    orchestrator,
                    aprovado=True,
                )

            # ---------------------------------------------
            # RUNTIME REPROVADO
            # ---------------------------------------------

            if (
                state.repair_attempts
                >= MAX_REPAIR_ATTEMPTS
            ):
                return finalizar_execucao(
                    state,
                    orchestrator,
                    aprovado=False,
                )

            orchestrator.begin_repair(
                state,
                origin="Runtime",
            )

            await executar_repair(
                contexto,
                tentativa=state.repair_attempts,
                origem="Runtime",
                hooks=hooks,
            )

            contexto.runtime_report = None

            orchestrator.transition(
                state,
                ProjectStage.QA,
            )
            orchestrator.activate_agent(
                state,
                "Project QA",
            )

            qa_report = await executar_qa(
                contexto,
                hooks,
            )

            exibir_qa(
                qa_report
            )

    except Exception as exc:
        orchestrator.fail(
            state,
            str(exc),
        )
        raise

    finally:
        project_trace.metadata.update(
            montar_trace_metadata(
                state
            )
        )
        project_trace.finish(
            reset_current=True
        )

# =========================================================
# ENTRADA SÍNCRONA PÚBLICA
# =========================================================

def run_project(
    pedido: str,
) -> ProjectState:
    """
    Entrada pública síncrona do Project Builder.

    Internamente todo o fluxo Agent SDK + MCP roda
    dentro de um único event loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop_ativo = False
    else:
        loop_ativo = True

    if loop_ativo:
        raise RuntimeError(
            "run_project() foi chamado dentro de um event loop ativo. "
            "Use: await run_project_async(pedido)"
        )

    return asyncio.run(
        run_project_async(
            pedido
        )
    )
