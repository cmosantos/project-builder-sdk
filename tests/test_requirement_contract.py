from types import SimpleNamespace

import pytest

from project_builder.agents import (
    architect_instructions,
    developer_instructions,
    qa_instructions,
    repair_instructions,
)
from project_builder.models import (
    ArchitecturePlan,
    ProjectContext,
)
from project_builder.orchestration.state import (
    ProjectState,
)


PEDIDO_ORIGINAL = (
    "Crie uma API de incidentes com categorias "
    "access, email, network, security e other; "
    "use apenas as transições OPEN -> IN_PROGRESS -> RESOLVED."
)


def criar_plano() -> ArchitecturePlan:
    return ArchitecturePlan(
        resumo=(
            "API FastAPI para triagem e acompanhamento "
            "de incidentes de suporte de TI."
        ),
        stack=[
            "Python 3.11+",
            "FastAPI",
            "Pydantic",
            "pytest",
        ],
        componentes=[
            "API de incidentes",
            "Store em memória",
        ],
        estrutura=[
            "app/main.py",
            "app/schemas.py",
            "app/store.py",
            "tests/test_api.py",
        ],
        requisitos=[
            (
                "Categorias permitidas: access, email, network, "
                "security e other."
            ),
            (
                "Transições: OPEN -> IN_PROGRESS -> RESOLVED."
            ),
        ],
        restricoes=[
            "Sem autenticação.",
            "Sem banco de dados externo.",
        ],
    )


def criar_wrapper() -> SimpleNamespace:
    contexto = ProjectContext(
        original_request=PEDIDO_ORIGINAL,
        architecture=criar_plano(),
    )

    return SimpleNamespace(
        context=contexto
    )


def test_project_state_preserva_pedido_original() -> None:
    state = ProjectState(
        request=PEDIDO_ORIGINAL
    )

    assert (
        state.context.original_request
        == PEDIDO_ORIGINAL
    )


def test_project_state_recusa_contexto_de_outro_pedido() -> None:
    contexto = ProjectContext(
        original_request="Outro pedido"
    )

    with pytest.raises(
        ValueError,
        match="pedido original diferente",
    ):
        ProjectState(
            request=PEDIDO_ORIGINAL,
            context=contexto,
        )


def test_architect_recebe_contrato_primario() -> None:
    instrucoes = architect_instructions(
        criar_wrapper(),
        None,
    )

    assert PEDIDO_ORIGINAL in instrucoes
    assert "contrato primário e imutável" in instrucoes
    assert "Não substitua valores explícitos" in instrucoes
    assert "Não remova valores de listas fechadas" in instrucoes


def test_developer_recebe_pedido_e_precedencia() -> None:
    instrucoes = developer_instructions(
        criar_wrapper(),
        None,
    )

    assert PEDIDO_ORIGINAL in instrucoes
    assert "PEDIDO ORIGINAL prevalece" in instrucoes
    assert "Categorias permitidas" in instrucoes

    assert (
        "Não remova requisitos explícitos "
        "porque não apareceram no plano."
        in instrucoes
    )


def test_qa_detecta_contrato_de_requirement_drift() -> None:
    instrucoes = qa_instructions(
        criar_wrapper(),
        None,
    )

    assert PEDIDO_ORIGINAL in instrucoes
    assert "DRIFT DE REQUISITO:" in instrucoes
    assert "o PEDIDO ORIGINAL prevalece" in instrucoes

    assert (
        "ArchitecturePlan apresentar drift de requisito"
        in instrucoes
    )


def test_repair_preserva_pedido_original() -> None:
    instrucoes = repair_instructions(
        criar_wrapper(),
        None,
    )

    assert PEDIDO_ORIGINAL in instrucoes
    assert "PEDIDO ORIGINAL prevalece" in instrucoes

    assert (
        "Repair não pode reescrever o ArchitecturePlan"
        in instrucoes
    )
