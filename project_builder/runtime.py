import json
import socket
import sys
import time

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from project_builder.config import WORKSPACE_ROOT
from project_builder.models import (
    RuntimeCheck,
    RuntimeReport,
)
from project_builder.sandbox import (
    SandboxCommandResult,
    SandboxExecutor,
)


# =========================================================
# CONFIGURAÇÃO
# =========================================================

OUTPUT_LIMIT = 12_000

DEFAULT_TIMEOUT = 60

PYTEST_TIMEOUT = 120

HTTP_STARTUP_TIMEOUT = 10

HTTP_REQUEST_TIMEOUT = 2

HTTP_POLL_INTERVAL = 0.25

SANDBOX_ROOT = (
    WORKSPACE_ROOT.parent
    / ".sandbox"
)


# =========================================================
# UTILIDADES
# =========================================================

def limitar_saida(
    texto: str,
) -> str:
    if not texto:
        return ""

    if len(texto) <= OUTPUT_LIMIT:
        return texto

    return (
        texto[:OUTPUT_LIMIT]
        + "\n\n... saída truncada ..."
    )


def obter_porta_livre() -> int:
    """
    Solicita ao sistema operacional uma porta
    TCP local atualmente disponível.
    """

    with socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    ) as sock:
        sock.bind(
            (
                "127.0.0.1",
                0,
            )
        )

        return int(
            sock.getsockname()[1]
        )


def converter_resultado(
    resultado: SandboxCommandResult,
) -> RuntimeCheck:
    return RuntimeCheck(
        nome=resultado.name,
        comando=resultado.command,
        return_code=resultado.return_code,
        stdout=limitar_saida(
            resultado.stdout
        ),
        stderr=limitar_saida(
            resultado.stderr
        ),
        sucesso=resultado.success,
    )


def _ler_resposta_http(
    url: str,
) -> tuple[int, str]:
    """
    Executa um GET real por loopback.

    Respostas HTTP 4xx continuam sendo respostas válidas
    do servidor e, por isso, são devolvidas ao chamador.
    Falhas de transporte permanecem como exceções.
    """

    request = Request(
        url,
        headers={
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(
            request,
            timeout=HTTP_REQUEST_TIMEOUT,
        ) as response:
            status = int(
                response.status
            )

            corpo = response.read().decode(
                "utf-8",
                errors="replace",
            )

            return (
                status,
                corpo,
            )

    except HTTPError as erro:
        corpo_bytes = (
            erro.read()
            if getattr(
                erro,
                "fp",
                None,
            ) is not None
            else b""
        )

        corpo = corpo_bytes.decode(
            "utf-8",
            errors="replace",
        )

        return (
            int(erro.code),
            corpo,
        )


def _status_confirma_liveness(
    status: int,
) -> bool:
    """
    Um status abaixo de 500 confirma que existe um
    servidor HTTP vivo respondendo naquele processo.

    404 e 405, por exemplo, podem ser perfeitamente
    válidos quando a aplicação não expõe a rota raiz.
    """

    return 100 <= status < 500


# =========================================================
# SMOKE TEST
# =========================================================

def executar_smoke_test(
    sandbox: SandboxExecutor,
) -> RuntimeCheck:
    resultado = sandbox.run(
        "smoke_test",
        timeout=DEFAULT_TIMEOUT,
    )

    return converter_resultado(
        resultado
    )


# =========================================================
# PYTEST
# =========================================================

def executar_pytest(
    sandbox: SandboxExecutor,
) -> RuntimeCheck:
    resultado = sandbox.run(
        "pytest",
        timeout=PYTEST_TIMEOUT,
    )

    return converter_resultado(
        resultado
    )


# =========================================================
# HTTP LIVE CHECK
# =========================================================

def executar_http_check(
    sandbox: SandboxExecutor,
) -> RuntimeCheck:
    """
    Sobe a cópia temporária da aplicação FastAPI dentro
    do SANDBOX_LOCAL e confirma comunicação HTTP real.

    Quando /openapi.json estiver habilitado, o check mantém
    a validação detalhada já existente.

    Quando OpenAPI estiver desabilitado, o check usa a rota
    raiz apenas como prova de liveness. Uma resposta HTTP
    abaixo de 500 confirma que Uvicorn e a aplicação estão
    vivos, mesmo que a rota raiz responda 404 ou 405.
    """

    porta = obter_porta_livre()

    host = "127.0.0.1"

    base_url = (
        f"http://{host}:{porta}"
    )

    openapi_url = (
        base_url
        + "/openapi.json"
    )

    root_url = (
        base_url
        + "/"
    )

    sandbox_process = None

    comando: list[str] = []

    sucesso = False

    return_code = -1

    stdout_check = ""

    stderr_check = ""

    ultimo_erro = ""

    try:
        sandbox_process = sandbox.start(
            "http_server",
            port=porta,
        )

        comando = (
            sandbox_process.command
        )

        processo = (
            sandbox_process.process
        )

        limite = (
            time.monotonic()
            + HTTP_STARTUP_TIMEOUT
        )

        while time.monotonic() < limite:

            # ---------------------------------------------
            # UVICORN MORREU ANTES DE RESPONDER
            # ---------------------------------------------

            if processo.poll() is not None:
                return_code = (
                    processo.returncode
                    if processo.returncode is not None
                    else -1
                )

                ultimo_erro = (
                    "O servidor Uvicorn encerrou "
                    "antes de responder ao HTTP check."
                )

                break

            try:
                # -----------------------------------------
                # 1. OPENAPI, QUANDO DISPONÍVEL
                # -----------------------------------------

                openapi_status, openapi_corpo = (
                    _ler_resposta_http(
                        openapi_url
                    )
                )

                if openapi_status == 200:
                    try:
                        dados = json.loads(
                            openapi_corpo
                        )

                    except json.JSONDecodeError:
                        dados = None

                    if isinstance(
                        dados,
                        dict,
                    ):
                        paths = dados.get(
                            "paths"
                        )

                        if (
                            "openapi" in dados
                            and isinstance(
                                paths,
                                dict,
                            )
                        ):
                            quantidade_rotas = len(
                                paths
                            )

                            stdout_check = "\n".join(
                                [
                                    "SANDBOX: SANDBOX_LOCAL",
                                    "HTTP LIVE CHECK OK",
                                    f"URL: {openapi_url}",
                                    "Status HTTP: 200",
                                    (
                                        "OpenAPI: "
                                        f"{dados.get('openapi')}"
                                    ),
                                    (
                                        "Rotas detectadas: "
                                        f"{quantidade_rotas}"
                                    ),
                                    "Modo: openapi",
                                ]
                            )

                            sucesso = True
                            return_code = 0

                            break

                # -----------------------------------------
                # 2. FALLBACK DE LIVENESS
                # -----------------------------------------
                #
                # O Runtime Gate não exige que OpenAPI
                # esteja habilitado. A validação funcional
                # da API já pertence ao pytest.
                # -----------------------------------------

                root_status, _ = (
                    _ler_resposta_http(
                        root_url
                    )
                )

                if _status_confirma_liveness(
                    root_status
                ):
                    stdout_check = "\n".join(
                        [
                            "SANDBOX: SANDBOX_LOCAL",
                            "HTTP LIVE CHECK OK",
                            f"URL: {root_url}",
                            (
                                "Status HTTP: "
                                f"{root_status}"
                            ),
                            "OpenAPI: indisponível",
                            (
                                "Rotas detectadas: "
                                "não verificadas"
                            ),
                            "Modo: liveness",
                        ]
                    )

                    sucesso = True
                    return_code = 0

                    break

                ultimo_erro = (
                    "A aplicação respondeu ao probe HTTP "
                    f"com status {root_status}."
                )

            except URLError as erro:
                ultimo_erro = (
                    "API ainda não disponível: "
                    f"{erro.reason}"
                )

            except TimeoutError:
                ultimo_erro = (
                    "Timeout aguardando resposta HTTP."
                )

            except ConnectionResetError as erro:
                ultimo_erro = (
                    "Conexão HTTP foi reiniciada durante "
                    f"a inicialização: {erro}"
                )

            except Exception as erro:
                ultimo_erro = (
                    "Erro inesperado durante "
                    "o HTTP Live Check: "
                    f"{type(erro).__name__}: {erro}"
                )

            time.sleep(
                HTTP_POLL_INTERVAL
            )

        if not sucesso and not ultimo_erro:
            ultimo_erro = (
                "A API não ficou disponível em "
                f"{HTTP_STARTUP_TIMEOUT} segundos."
            )

    except Exception as erro:
        ultimo_erro = (
            "Falha ao iniciar o Uvicorn no "
            "SANDBOX_LOCAL: "
            f"{type(erro).__name__}: {erro}"
        )

    finally:
        servidor_stdout = ""

        servidor_stderr = ""

        if sandbox_process is not None:
            (
                servidor_stdout,
                servidor_stderr,
            ) = sandbox.stop(
                sandbox_process
            )

        if not sucesso:
            partes_erro: list[str] = []

            if ultimo_erro:
                partes_erro.append(
                    ultimo_erro
                )

            if servidor_stderr.strip():
                partes_erro.append(
                    "STDERR DO UVICORN:\n"
                    + servidor_stderr.strip()
                )

            if servidor_stdout.strip():
                partes_erro.append(
                    "STDOUT DO UVICORN:\n"
                    + servidor_stdout.strip()
                )

            stderr_check = "\n\n".join(
                partes_erro
            )

    return RuntimeCheck(
        nome="http_check",
        comando=comando,
        return_code=return_code,
        stdout=limitar_saida(
            stdout_check
        ),
        stderr=limitar_saida(
            stderr_check
        ),
        sucesso=sucesso,
    )


# =========================================================
# CHECK NÃO EXECUTADO
# =========================================================

def check_nao_executado(
    nome: str,
    motivo: str,
) -> RuntimeCheck:
    return RuntimeCheck(
        nome=nome,
        comando=[],
        return_code=-1,
        stdout="",
        stderr=motivo,
        sucesso=False,
    )


# =========================================================
# RUNTIME GATE
# =========================================================

def executar_runtime_gate() -> RuntimeReport:
    """
    Executa o Runtime Gate em uma cópia temporária
    do workspace usando SANDBOX_LOCAL.

    A cópia é removida ao sair do bloco, inclusive
    quando um gate falha ou uma exceção é lançada.
    """

    with SandboxExecutor(
        source_workspace=WORKSPACE_ROOT,
        sandbox_root=SANDBOX_ROOT,
        python_executable=sys.executable,
    ) as sandbox:

        # -------------------------------------------------
        # 1. SMOKE TEST
        # -------------------------------------------------

        smoke_test = executar_smoke_test(
            sandbox
        )

        if not smoke_test.sucesso:
            pytest = check_nao_executado(
                nome="pytest",
                motivo=(
                    "Pytest não executado porque "
                    "o smoke test falhou."
                ),
            )

            http_check = check_nao_executado(
                nome="http_check",
                motivo=(
                    "HTTP Live Check não executado porque "
                    "o smoke test falhou."
                ),
            )

            return RuntimeReport(
                status="REPROVADO",
                python_executable=sys.executable,
                smoke_test=smoke_test,
                pytest=pytest,
                http_check=http_check,
            )

        # -------------------------------------------------
        # 2. PYTEST
        # -------------------------------------------------

        pytest = executar_pytest(
            sandbox
        )

        if not pytest.sucesso:
            http_check = check_nao_executado(
                nome="http_check",
                motivo=(
                    "HTTP Live Check não executado porque "
                    "o pytest falhou."
                ),
            )

            return RuntimeReport(
                status="REPROVADO",
                python_executable=sys.executable,
                smoke_test=smoke_test,
                pytest=pytest,
                http_check=http_check,
            )

        # -------------------------------------------------
        # 3. HTTP LIVE CHECK
        # -------------------------------------------------

        http_check = executar_http_check(
            sandbox
        )

        status = (
            "APROVADO"
            if http_check.sucesso
            else "REPROVADO"
        )

        return RuntimeReport(
            status=status,
            python_executable=sys.executable,
            smoke_test=smoke_test,
            pytest=pytest,
            http_check=http_check,
        )