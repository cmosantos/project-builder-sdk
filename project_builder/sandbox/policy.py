from dataclasses import dataclass


SMOKE_CODE = (
    "from app.main import app; "
    "print('FASTAPI APP OK'); "
    "print(type(app).__name__)"
)


@dataclass(frozen=True)
class SandboxPolicy:
    allowed_host: str = "127.0.0.1"
    max_timeout_seconds: int = 120

    def build_arguments(
        self,
        operation: str,
        *,
        port: int | None = None,
    ) -> list[str]:
        if operation == "smoke_test":
            return [
                "-c",
                SMOKE_CODE,
            ]

        if operation == "pytest":
            return [
                "-m",
                "pytest",
                "tests",
                "-q",
            ]

        if operation == "http_server":
            if port is None:
                raise ValueError(
                    "A operação http_server exige uma porta."
                )

            if not 1 <= port <= 65535:
                raise ValueError(
                    "Porta fora do intervalo TCP válido."
                )

            return [
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                self.allowed_host,
                "--port",
                str(port),
                "--log-level",
                "warning",
            ]

        raise ValueError(
            f"Operação não permitida pelo sandbox: {operation}"
        )

    def validate_timeout(
        self,
        timeout: int,
    ) -> None:
        if timeout <= 0:
            raise ValueError(
                "O timeout deve ser maior que zero."
            )

        if timeout > self.max_timeout_seconds:
            raise ValueError(
                "Timeout excede o limite do sandbox: "
                f"{timeout}s > {self.max_timeout_seconds}s."
            )