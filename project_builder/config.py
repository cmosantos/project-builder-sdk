from pathlib import Path


# Raiz do projeto:
# C:\Projetos\project-builder-sdk
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# Workspace onde os projetos gerados são criados
WORKSPACE_ROOT = PROJECT_ROOT / "workspace"

WORKSPACE_ROOT.mkdir(exist_ok=True)


# Arquivos permitidos no MVP atual
EXPECTED_FILES = (
    "app/__init__.py",
    "app/main.py",
    "app/schemas.py",
    "app/store.py",
    "tests/test_api.py",
    "requirements.txt",
    "README.md",
)

EXPECTED_FILE_SET = set(EXPECTED_FILES)