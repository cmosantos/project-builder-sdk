import shutil
from pathlib import Path

from agents import (
    RunContextWrapper,
    function_tool,
)

from project_builder.config import (
    EXPECTED_FILES,
    EXPECTED_FILE_SET,
    PROJECT_ROOT,
    WORKSPACE_ROOT,
)
from project_builder.models import (
    ProjectContext,
    ProjectFile,
)


# =========================================================
# CAMINHOS
# =========================================================

def normalizar_caminho(
    caminho: str,
) -> str:
    return caminho.strip().replace(
        "\\",
        "/",
    )


def caminho_seguro(
    caminho_relativo: str,
) -> Path:
    caminho_normalizado = normalizar_caminho(
        caminho_relativo
    )

    if caminho_normalizado not in EXPECTED_FILE_SET:
        raise ValueError(
            "Arquivo fora do contrato permitido: "
            f"{caminho_normalizado}"
        )

    workspace = WORKSPACE_ROOT.resolve()

    destino = (
        WORKSPACE_ROOT
        / caminho_normalizado
    ).resolve()

    if workspace not in destino.parents:
        raise ValueError(
            "Tentativa de acesso fora do workspace."
        )

    return destino


# =========================================================
# LIFECYCLE DO WORKSPACE
# =========================================================

def _diretorios_permitidos() -> set[str]:
    """
    Retorna todos os diretorios necessarios para os
    arquivos definidos em EXPECTED_FILES.
    """

    permitidos: set[str] = set()

    for caminho in EXPECTED_FILES:
        caminho_path = Path(
            normalizar_caminho(caminho)
        )

        for pai in caminho_path.parents:
            if pai == Path("."):
                continue

            permitidos.add(
                pai.as_posix()
            )

    return permitidos


def limpar_workspace() -> list[str]:
    """
    Remove somente residuos que nao pertencem ao contrato.

    Arquivos oficiais e os diretorios necessarios para eles
    sao preservados. Exemplos de residuos removidos:

    - pytest.ini
    - lixo.txt
    - .pytest_cache/
    - app/legacy.py
    - tests/test_antigo.py
    - qualquer diretorio inesperado
    """

    project_root = PROJECT_ROOT.resolve()
    workspace = WORKSPACE_ROOT.resolve()

    if (
        workspace == project_root
        or project_root not in workspace.parents
    ):
        raise RuntimeError(
            "Workspace invalido para limpeza segura: "
            f"{workspace}"
        )

    workspace.mkdir(
        parents=True,
        exist_ok=True,
    )

    arquivos_permitidos = {
        normalizar_caminho(caminho)
        for caminho in EXPECTED_FILES
    }

    diretorios_permitidos = (
        _diretorios_permitidos()
    )

    removidos: list[str] = []

    def limpar_diretorio(
        diretorio: Path,
    ) -> None:
        for item in sorted(
            diretorio.iterdir(),
            key=lambda path: path.name.lower(),
        ):
            relativo = item.relative_to(
                workspace
            ).as_posix()

            # Symlinks nunca fazem parte do contrato.
            if item.is_symlink():
                item.unlink()

                removidos.append(
                    relativo
                )

                continue

            if item.is_file():
                if relativo in arquivos_permitidos:
                    continue

                item.unlink()

                removidos.append(
                    relativo
                )

                continue

            if item.is_dir():
                if relativo not in diretorios_permitidos:
                    shutil.rmtree(
                        item
                    )

                    removidos.append(
                        relativo + "/"
                    )

                    continue

                limpar_diretorio(
                    item
                )

                continue

            item.unlink()

            removidos.append(
                relativo
            )

    limpar_diretorio(
        workspace
    )

    return removidos


# =========================================================
# CRIACAO INICIAL
# =========================================================

@function_tool
def criar_projeto(
    context: RunContextWrapper[ProjectContext],
    arquivos: list[ProjectFile],
) -> str:
    """
    Cria a implementacao inicial do projeto.

    Esta ferramenta pode ser utilizada somente
    uma vez por execucao.
    """

    if context.context.created_files:
        raise RuntimeError(
            "O projeto ja foi criado nesta execucao."
        )

    if not arquivos:
        raise ValueError(
            "Nenhum arquivo foi recebido."
        )

    caminhos = [
        normalizar_caminho(
            arquivo.caminho
        )
        for arquivo in arquivos
    ]

    if len(caminhos) != len(set(caminhos)):
        raise ValueError(
            "Existem caminhos duplicados "
            "na solicitacao."
        )

    recebidos = set(caminhos)

    faltando = (
        EXPECTED_FILE_SET - recebidos
    )

    extras = (
        recebidos - EXPECTED_FILE_SET
    )

    if faltando or extras:
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

        raise ValueError(
            "Contrato de arquivos invalido: "
            + " | ".join(detalhes)
        )

    # Primeiro valida TODOS os destinos.
    # Nada no workspace e alterado enquanto a entrega
    # completa nao tiver sido validada.
    destinos: list[
        tuple[str, Path, str]
    ] = []

    for arquivo in arquivos:
        caminho = normalizar_caminho(
            arquivo.caminho
        )

        destino = caminho_seguro(
            caminho
        )

        destinos.append(
            (
                caminho,
                destino,
                arquivo.conteudo,
            )
        )

    # Remove somente residuos de execucoes anteriores.
    # Os arquivos e diretorios oficiais sao preservados.
    removidos = limpar_workspace()

    if removidos:
        print(
            "  Workspace preparado: "
            f"{len(removidos)} residuo(s) removido(s)"
        )
    else:
        print(
            "  Workspace preparado: sem residuos"
        )

    # Todos os sete arquivos oficiais sao sobrescritos
    # pela nova geracao.
    for (
        caminho,
        destino,
        conteudo,
    ) in destinos:
        destino.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        texto = conteudo.rstrip() + "\n"

        destino.write_text(
            texto,
            encoding="utf-8",
        )

        context.context.created_files.append(
            caminho
        )

        print(
            f"  Developer criou {caminho}"
        )

    return (
        "Projeto criado com sucesso. "
        f"{len(destinos)} arquivos gravados."
    )


# =========================================================
# REPARO
# =========================================================

@function_tool
def reparar_projeto(
    context: RunContextWrapper[ProjectContext],
    arquivos: list[ProjectFile],
) -> str:
    """
    Atualiza somente arquivos existentes do projeto.

    Pode receber um subconjunto dos arquivos permitidos.
    E utilizada pelo Repair Agent depois que QA ou
    Runtime encontram problemas.
    """

    if not context.context.created_files:
        raise RuntimeError(
            "Nao existe projeto criado "
            "para ser reparado."
        )

    if not arquivos:
        raise ValueError(
            "Nenhum arquivo foi informado "
            "para reparo."
        )

    caminhos = [
        normalizar_caminho(
            arquivo.caminho
        )
        for arquivo in arquivos
    ]

    if len(caminhos) != len(set(caminhos)):
        raise ValueError(
            "Existem caminhos duplicados "
            "na solicitacao de reparo."
        )

    extras = (
        set(caminhos)
        - EXPECTED_FILE_SET
    )

    if extras:
        raise ValueError(
            "Reparo tentou acessar arquivos "
            "fora do contrato: "
            + ", ".join(
                sorted(extras)
            )
        )

    destinos: list[
        tuple[str, Path, str]
    ] = []

    # Valida tudo antes de alterar qualquer arquivo.
    for arquivo in arquivos:
        caminho = normalizar_caminho(
            arquivo.caminho
        )

        destino = caminho_seguro(
            caminho
        )

        if not destino.exists():
            raise FileNotFoundError(
                "Repair Agent tentou alterar "
                "arquivo inexistente: "
                f"{caminho}"
            )

        destinos.append(
            (
                caminho,
                destino,
                arquivo.conteudo,
            )
        )

    # Depois da validacao completa, aplica as alteracoes.
    for (
        caminho,
        destino,
        conteudo,
    ) in destinos:
        texto = conteudo.rstrip() + "\n"

        destino.write_text(
            texto,
            encoding="utf-8",
        )

        print(
            f"  Repair corrigiu {caminho}"
        )

    return (
        "Reparo aplicado com sucesso. "
        f"{len(destinos)} arquivo(s) atualizado(s): "
        + ", ".join(caminhos)
    )


# =========================================================
# COLETA PARA QA / REPAIR
# =========================================================

@function_tool
def coletar_workspace(
    context: RunContextWrapper[ProjectContext],
) -> str:
    """
    Retorna o conteudo completo dos arquivos
    permitidos do workspace.
    """

    if not context.context.created_files:
        raise RuntimeError(
            "Nenhum projeto foi criado "
            "nesta execucao."
        )

    blocos: list[str] = []

    total_caracteres = 0

    limite_total = 100_000

    for caminho in EXPECTED_FILES:
        destino = caminho_seguro(
            caminho
        )

        if not destino.exists():
            raise FileNotFoundError(
                "Arquivo obrigatorio ausente: "
                f"{caminho}"
            )

        conteudo = destino.read_text(
            encoding="utf-8"
        )

        total_caracteres += len(
            conteudo
        )

        if total_caracteres > limite_total:
            raise RuntimeError(
                "Workspace excedeu o limite "
                "de leitura permitido."
            )

        blocos.append(
            "\n".join(
                [
                    "=" * 70,
                    f"ARQUIVO: {caminho}",
                    "=" * 70,
                    conteudo,
                ]
            )
        )

    print(
        "  Workspace coletado"
    )

    return "\n\n".join(blocos)


# =========================================================
# VALIDACAO FISICA
# =========================================================

def validar_arquivos_no_disco() -> list[str]:
    ausentes: list[str] = []

    for caminho in EXPECTED_FILES:
        destino = caminho_seguro(
            caminho
        )

        if not destino.exists():
            ausentes.append(
                caminho
            )

    return ausentes
