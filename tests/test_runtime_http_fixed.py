import json
from types import SimpleNamespace
from urllib.error import HTTPError

import project_builder.runtime as runtime_module


class FakeProcess:
    returncode = None

    def poll(self):
        return None


class FakeSandbox:
    def start(
        self,
        operation,
        *,
        port,
    ):
        return SimpleNamespace(
            command=[
                "python",
                "-m",
                "uvicorn",
                "app.main:app",
            ],
            process=FakeProcess(),
        )

    def stop(
        self,
        sandbox_process,
    ):
        return (
            "",
            "",
        )


class FakeResponse:
    def __init__(
        self,
        status,
        payload,
    ):
        self.status = status
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        return False

    def read(self):
        return self._payload


def test_http_live_check_accepts_openapi_disabled(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime_module,
        "obter_porta_livre",
        lambda: 8765,
    )

    def fake_urlopen(
        request,
        timeout,
    ):
        url = request.full_url

        raise HTTPError(
            url=url,
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(
        runtime_module,
        "urlopen",
        fake_urlopen,
    )

    resultado = (
        runtime_module.executar_http_check(
            FakeSandbox()
        )
    )

    assert resultado.sucesso is True
    assert resultado.return_code == 0
    assert "Status HTTP: 404" in resultado.stdout
    assert "OpenAPI: indisponível" in resultado.stdout
    assert "Modo: liveness" in resultado.stdout


def test_http_live_check_preserves_openapi_mode(
    monkeypatch,
):
    monkeypatch.setattr(
        runtime_module,
        "obter_porta_livre",
        lambda: 8765,
    )

    payload = json.dumps(
        {
            "openapi": "3.1.0",
            "paths": {
                "/health": {},
                "/items": {},
            },
        }
    ).encode(
        "utf-8"
    )

    def fake_urlopen(
        request,
        timeout,
    ):
        return FakeResponse(
            200,
            payload,
        )

    monkeypatch.setattr(
        runtime_module,
        "urlopen",
        fake_urlopen,
    )

    resultado = (
        runtime_module.executar_http_check(
            FakeSandbox()
        )
    )

    assert resultado.sucesso is True
    assert resultado.return_code == 0
    assert "Status HTTP: 200" in resultado.stdout
    assert "OpenAPI: 3.1.0" in resultado.stdout
    assert "Rotas detectadas: 2" in resultado.stdout
    assert "Modo: openapi" in resultado.stdout