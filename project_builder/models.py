from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


# =========================================================
# ARQUITETURA
# =========================================================

class ArchitecturePlan(BaseModel):
    resumo: str = Field(
        min_length=20,
        max_length=800,
    )

    stack: list[str] = Field(
        min_length=1,
        max_length=10,
    )

    componentes: list[str] = Field(
        min_length=1,
        max_length=12,
    )

    estrutura: list[str] = Field(
        min_length=1,
        max_length=12,
    )

    requisitos: list[str] = Field(
        min_length=1,
        max_length=15,
    )

    restricoes: list[str] = Field(
        min_length=1,
        max_length=10,
    )


# =========================================================
# ARQUIVOS
# =========================================================

class ProjectFile(BaseModel):
    caminho: str = Field(
        min_length=1
    )

    conteudo: str = Field(
        min_length=1
    )


# =========================================================
# QA
# =========================================================

class QAReport(BaseModel):
    status: Literal[
        "APROVADO",
        "REPROVADO",
    ]

    score: int = Field(
        ge=0,
        le=100,
    )

    resumo: str = Field(
        min_length=20,
        max_length=1000,
    )

    arquivos_revisados: list[str]

    verificacoes_aprovadas: list[str]

    problemas_encontrados: list[str]

    recomendacoes: list[str]


# =========================================================
# RUNTIME
# =========================================================

class RuntimeCheck(BaseModel):
    nome: str

    comando: list[str]

    return_code: int

    stdout: str

    stderr: str

    sucesso: bool


class RuntimeReport(BaseModel):
    status: Literal[
        "APROVADO",
        "REPROVADO",
    ]

    python_executable: str

    smoke_test: RuntimeCheck

    pytest: RuntimeCheck

    http_check: RuntimeCheck | None = None


# =========================================================
# CONTEXTO DO WORKFLOW
# =========================================================

@dataclass
class ProjectContext:
    original_request: str = ""

    architecture: ArchitecturePlan | None = None

    created_files: list[str] = field(
        default_factory=list
    )

    qa_report: QAReport | None = None

    runtime_report: RuntimeReport | None = None