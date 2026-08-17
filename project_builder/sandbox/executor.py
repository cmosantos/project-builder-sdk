from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from project_builder.sandbox.policy import SandboxPolicy


@dataclass
class SandboxCommandResult:
    name: str
    command: list[str]
    return_code: int
    stdout: str
    stderr: str
    success: bool


@dataclass
class SandboxProcess:
    name: str
    command: list[str]
    process: subprocess.Popen


class SandboxExecutor:
    """
    Executor local controlado.

    SANDBOX_LOCAL não é isolamento de kernel ou container.
    Ele executa uma cópia temporária do workspace, aceita
    somente operações definidas pela SandboxPolicy, aplica
    timeouts e encerra processos registrados no cleanup.
    """

    mode = "SANDBOX_LOCAL"

    def __init__(
        self,
        source_workspace: Path,
        sandbox_root: Path,
        *,
        python_executable: str | None = None,
        policy: SandboxPolicy | None = None,
    ) -> None:
        self.source_workspace = source_workspace.resolve()
        self.sandbox_root = sandbox_root.resolve()
        self.python_executable = (
            python_executable
            or sys.executable
        )
        self.policy = (
            policy
            or SandboxPolicy()
        )

        self.workspace: Path | None = None
        self._processes: list[SandboxProcess] = []

    def __enter__(
        self,
    ) -> "SandboxExecutor":
        self.prepare()
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> None:
        self.cleanup()

    def prepare(
        self,
    ) -> Path:
        if self.workspace is not None:
            return self.workspace

        if not self.source_workspace.exists():
            raise RuntimeError(
                "Workspace de origem não encontrado: "
                f"{self.source_workspace}"
            )

        if not self.source_workspace.is_dir():
            raise RuntimeError(
                "Workspace de origem não é um diretório: "
                f"{self.source_workspace}"
            )

        self.sandbox_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        run_dir = Path(
            tempfile.mkdtemp(
                prefix="run-",
                dir=self.sandbox_root,
            )
        ).resolve()

        shutil.copytree(
            self.source_workspace,
            run_dir,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                ".pytest_cache",
            ),
        )

        self.workspace = run_dir

        return run_dir

    def _require_workspace(
        self,
    ) -> Path:
        if self.workspace is None:
            raise RuntimeError(
                "Sandbox não preparado."
            )

        return self.workspace

    def _environment(
        self,
    ) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONNOUSERSITE"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"

        return env

    def run(
        self,
        operation: str,
        *,
        timeout: int,
    ) -> SandboxCommandResult:
        self.policy.validate_timeout(
            timeout
        )

        argumentos = (
            self.policy.build_arguments(
                operation
            )
        )

        comando = [
            self.python_executable,
            *argumentos,
        ]

        workspace = (
            self._require_workspace()
        )

        try:
            resultado = subprocess.run(
                comando,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                shell=False,
                env=self._environment(),
            )

            return SandboxCommandResult(
                name=operation,
                command=comando,
                return_code=resultado.returncode,
                stdout=resultado.stdout or "",
                stderr=resultado.stderr or "",
                success=(
                    resultado.returncode == 0
                ),
            )

        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or ""
            stderr = error.stderr or ""

            if isinstance(
                stdout,
                bytes,
            ):
                stdout = stdout.decode(
                    errors="replace"
                )

            if isinstance(
                stderr,
                bytes,
            ):
                stderr = stderr.decode(
                    errors="replace"
                )

            mensagem = (
                stderr
                + "\n"
                + (
                    "Timeout do SANDBOX_LOCAL "
                    f"após {timeout} segundos."
                )
            ).strip()

            return SandboxCommandResult(
                name=operation,
                command=comando,
                return_code=-1,
                stdout=stdout,
                stderr=mensagem,
                success=False,
            )

    def start(
        self,
        operation: str,
        *,
        port: int,
    ) -> SandboxProcess:
        argumentos = (
            self.policy.build_arguments(
                operation,
                port=port,
            )
        )

        comando = [
            self.python_executable,
            *argumentos,
        ]

        workspace = (
            self._require_workspace()
        )

        processo = subprocess.Popen(
            comando,
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            env=self._environment(),
        )

        registro = SandboxProcess(
            name=operation,
            command=comando,
            process=processo,
        )

        self._processes.append(
            registro
        )

        return registro

    def stop(
        self,
        sandbox_process: SandboxProcess,
    ) -> tuple[str, str]:
        processo = sandbox_process.process

        if processo.poll() is None:
            processo.terminate()

            try:
                processo.wait(
                    timeout=5
                )

            except subprocess.TimeoutExpired:
                processo.kill()
                processo.wait(
                    timeout=5
                )

        try:
            stdout, stderr = (
                processo.communicate(
                    timeout=2
                )
            )

        except subprocess.TimeoutExpired:
            processo.kill()
            stdout, stderr = (
                processo.communicate()
            )

        if sandbox_process in self._processes:
            self._processes.remove(
                sandbox_process
            )

        return (
            stdout or "",
            stderr or "",
        )

    def cleanup(
        self,
    ) -> None:
        for sandbox_process in list(
            self._processes
        ):
            try:
                self.stop(
                    sandbox_process
                )
            except Exception:
                pass

        if self.workspace is not None:
            shutil.rmtree(
                self.workspace,
                ignore_errors=True,
            )
            self.workspace = None

        try:
            self.sandbox_root.rmdir()
        except OSError:
            pass