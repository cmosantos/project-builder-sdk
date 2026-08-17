import os
from pathlib import Path

try:
    from mcp.server import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer


MCP_NAME = "Project Builder Workspace"

MAX_FILE_BYTES = 120_000
MAX_SEARCH_MATCHES = 50
MAX_SNAPSHOT_BYTES = 180_000

IGNORED_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".git",
    ".venv",
}

mcp = MCPServer(MCP_NAME)


def _workspace_root() -> Path:
    raw = os.environ.get(
        "PROJECT_BUILDER_MCP_WORKSPACE",
        "",
    ).strip()

    if not raw:
        raise RuntimeError(
            "PROJECT_BUILDER_MCP_WORKSPACE não definido."
        )

    root = Path(raw).resolve()

    if not root.exists():
        raise RuntimeError(
            f"Workspace MCP não encontrado: {root}"
        )

    if not root.is_dir():
        raise RuntimeError(
            f"Workspace MCP não é diretório: {root}"
        )

    return root


def _resolve_relative(
    relative_path: str,
) -> Path:
    root = _workspace_root()
    relative = Path(relative_path)

    if relative.is_absolute():
        raise ValueError(
            "Caminhos absolutos não são permitidos."
        )

    target = (
        root
        / relative
    ).resolve()

    if not target.is_relative_to(root):
        raise ValueError(
            "Acesso fora do workspace não é permitido."
        )

    return target


def _iter_workspace_files() -> list[Path]:
    root = _workspace_root()
    files: list[Path] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        relative_parts = (
            path.relative_to(root).parts
        )

        if any(
            part in IGNORED_DIRS
            for part in relative_parts
        ):
            continue

        files.append(path)

    return sorted(
        files,
        key=lambda item: item.as_posix(),
    )


def _list_workspace_files() -> list[str]:
    root = _workspace_root()

    return [
        path.relative_to(root).as_posix()
        for path in _iter_workspace_files()
    ]


def _read_workspace_file(
    relative_path: str,
) -> str:
    target = _resolve_relative(
        relative_path
    )

    if not target.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {relative_path}"
        )

    if not target.is_file():
        raise ValueError(
            f"O caminho não é arquivo: {relative_path}"
        )

    size = target.stat().st_size

    if size > MAX_FILE_BYTES:
        raise ValueError(
            "Arquivo excede o limite de leitura MCP: "
            f"{size} bytes > {MAX_FILE_BYTES} bytes."
        )

    return target.read_text(
        encoding="utf-8",
        errors="replace",
    )



def _workspace_snapshot() -> dict[str, object]:
    root = _workspace_root()
    files: list[dict[str, str]] = []
    total_bytes = 0

    for path in _iter_workspace_files():
        size = path.stat().st_size

        if size > MAX_FILE_BYTES:
            raise ValueError(
                "Arquivo excede o limite de leitura MCP: "
                f"{path.relative_to(root).as_posix()} "
                f"({size} bytes > {MAX_FILE_BYTES} bytes)."
            )

        total_bytes += size

        if total_bytes > MAX_SNAPSHOT_BYTES:
            raise ValueError(
                "Workspace excede o limite do snapshot MCP: "
                f"{total_bytes} bytes > {MAX_SNAPSHOT_BYTES} bytes."
            )

        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "content": path.read_text(
                    encoding="utf-8",
                    errors="replace",
                ),
            }
        )

    return {
        "mode": "read-only",
        "file_count": len(files),
        "total_bytes": total_bytes,
        "files": files,
    }

def _search_workspace_text(
    query: str,
) -> list[dict[str, object]]:
    query = query.strip()

    if not query:
        raise ValueError(
            "A busca MCP não pode ser vazia."
        )

    root = _workspace_root()
    needle = query.casefold()
    matches: list[dict[str, object]] = []

    for path in _iter_workspace_files():
        if path.stat().st_size > MAX_FILE_BYTES:
            continue

        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            continue

        for line_number, line in enumerate(
            text.splitlines(),
            start=1,
        ):
            if needle not in line.casefold():
                continue

            matches.append(
                {
                    "file": path.relative_to(root).as_posix(),
                    "line": line_number,
                    "text": line.strip(),
                }
            )

            if len(matches) >= MAX_SEARCH_MATCHES:
                return matches

    return matches


@mcp.tool()
def workspace_snapshot() -> dict[str, object]:
    """Retorna todos os arquivos do workspace em um snapshot somente leitura."""
    return _workspace_snapshot()


@mcp.tool()
def workspace_list() -> list[str]:
    """Lista os arquivos do workspace atual. Somente leitura."""
    return _list_workspace_files()


@mcp.tool()
def workspace_read(
    path: str,
) -> str:
    """Lê um arquivo relativo ao workspace. Somente leitura."""
    return _read_workspace_file(
        path
    )


@mcp.tool()
def workspace_search(
    query: str,
) -> list[dict[str, object]]:
    """Pesquisa texto nos arquivos do workspace. Somente leitura."""
    return _search_workspace_text(
        query
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
