import os

from project_builder.config import WORKSPACE_ROOT


FAULT_ENV = "PROJECT_BUILDER_FAULT_INJECTION"

FAULT_PATCH_AS_POST = "patch_as_post"


def aplicar_fault_injection() -> str | None:
    """
    Injeta uma falha proposital no projeto gerado.

    Uso exclusivo para validação do Repair Loop.

    Sem a variável de ambiente configurada,
    nenhuma alteração é realizada.
    """

    modo = os.getenv(
        FAULT_ENV,
        "",
    ).strip().lower()

    if not modo:
        return None

    if modo == FAULT_PATCH_AS_POST:
        return _trocar_primeiro_patch_por_post()

    raise ValueError(
        "Fault injection desconhecido: "
        f"{modo}"
    )


def _trocar_primeiro_patch_por_post() -> str:
    """
    Troca propositalmente o primeiro decorator
    @app.patch por @app.post.

    O código Python permanece válido, porém
    o endpoint PATCH deixa de existir como PATCH.

    Isso permite validar de forma determinística:

    QA -> REPROVADO -> Repair -> QA -> Runtime
    """

    arquivo = (
        WORKSPACE_ROOT
        / "app"
        / "main.py"
    )

    if not arquivo.exists():
        raise FileNotFoundError(
            "Não foi possível aplicar fault injection: "
            "app/main.py não existe."
        )

    conteudo = arquivo.read_text(
        encoding="utf-8"
    )

    alvo = "@app.patch("

    if alvo not in conteudo:
        raise RuntimeError(
            "Não foi encontrado endpoint PATCH "
            "para aplicar o fault injection."
        )

    conteudo_alterado = conteudo.replace(
        alvo,
        "@app.post(",
        1,
    )

    arquivo.write_text(
        conteudo_alterado,
        encoding="utf-8",
    )

    return (
        "FAULT INJECTION aplicado: "
        "o primeiro endpoint PATCH foi "
        "convertido propositalmente em POST."
    )