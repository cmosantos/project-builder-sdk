import asyncio
import json
import os
from pathlib import Path
import sys
from typing import Any

from agents import custom_span
from agents.mcp import MCPServerStdio

from project_builder.config import WORKSPACE_ROOT


MCP_CLIENT_TIMEOUT_SECONDS = 15
MCP_OPERATION_TIMEOUT_SECONDS = 30

SERVER_PATH = (
    Path(__file__)
    .with_name("workspace_server.py")
    .resolve()
)


def create_workspace_mcp_server() -> MCPServerStdio:
    env = os.environ.copy()
    env[
        "PROJECT_BUILDER_MCP_WORKSPACE"
    ] = str(
        WORKSPACE_ROOT.resolve()
    )

    return MCPServerStdio(
        name="Project Builder Workspace",
        params={
            "command": sys.executable,
            "args": [
                str(SERVER_PATH),
            ],
            "env": env,
        },
        cache_tools_list=True,
        client_session_timeout_seconds=(
            MCP_CLIENT_TIMEOUT_SECONDS
        ),
    )


def _result_to_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        return result.model_dump(
            mode="python",
            by_alias=True,
        )

    if isinstance(result, dict):
        return result

    raise RuntimeError(
        "Resposta MCP não pôde ser serializada."
    )


def _extract_snapshot(
    result: Any,
) -> dict[str, Any]:
    payload = _result_to_dict(result)

    structured = (
        payload.get("structuredContent")
        or payload.get("structured_content")
    )

    if isinstance(structured, dict):
        snapshot = structured
    else:
        snapshot = None

        for item in payload.get("content", []):
            if isinstance(item, dict):
                text = item.get("text")
            else:
                text = getattr(
                    item,
                    "text",
                    None,
                )

            if not isinstance(text, str):
                continue

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict):
                snapshot = parsed
                break

    if not isinstance(snapshot, dict):
        raise RuntimeError(
            "workspace_snapshot não retornou "
            "um objeto estruturado."
        )

    files = snapshot.get("files")

    if not isinstance(files, list):
        raise RuntimeError(
            "workspace_snapshot não retornou "
            "a lista de arquivos esperada."
        )

    return snapshot


async def _read_workspace_snapshot_mcp() -> dict[str, Any]:
    async def operation() -> dict[str, Any]:
        with custom_span(
            "mcp.workspace_snapshot",
            {
                "server": "Project Builder Workspace",
                "mode": "read-only",
                "transport": "stdio",
            },
        ):
            async with (
                create_workspace_mcp_server()
                as server
            ):
                result = await server.call_tool(
                    "workspace_snapshot",
                    {},
                )

                return _extract_snapshot(
                    result
                )

    try:
        return await asyncio.wait_for(
            operation(),
            timeout=MCP_OPERATION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError(
            "Leitura MCP workspace_snapshot excedeu "
            f"{MCP_OPERATION_TIMEOUT_SECONDS} segundos."
        ) from exc



async def read_workspace_snapshot_mcp() -> dict[str, Any]:
    """
    Lê o snapshot MCP usando o event loop atual.
    """
    return await _read_workspace_snapshot_mcp()

def read_workspace_snapshot_mcp_sync() -> dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "read_workspace_snapshot_mcp_sync não pode "
            "ser chamado dentro de um event loop ativo."
        )

    return asyncio.run(
        _read_workspace_snapshot_mcp()
    )


async def _verify_workspace_mcp() -> list[str]:
    async def operation() -> list[str]:
        async with (
            create_workspace_mcp_server()
            as server
        ):
            tools = await server.list_tools()

            return sorted(
                tool.name
                for tool in tools
            )

    try:
        return await asyncio.wait_for(
            operation(),
            timeout=MCP_OPERATION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError(
            "Validação MCP excedeu "
            f"{MCP_OPERATION_TIMEOUT_SECONDS} segundos."
        ) from exc


def verify_workspace_mcp_sync() -> list[str]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "verify_workspace_mcp_sync não pode "
            "ser chamado dentro de um event loop ativo."
        )

    return asyncio.run(
        _verify_workspace_mcp()
    )
