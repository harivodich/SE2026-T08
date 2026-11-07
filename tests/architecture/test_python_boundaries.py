"""Import boundaries for the Python compute package (AST, no execution)."""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parents[2] / "src" / "vietdoc"
WEB = {"fastapi", "starlette", "uvicorn"}
MODEL = {"torch", "transformers", "peft", "accelerate", "paddle", "paddleocr"}
DATABASE = {"sqlalchemy", "psycopg", "psycopg2", "asyncpg", "sqlite3", "alembic", "celery", "redis"}


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def sources(*parts: str) -> list[Path]:
    return sorted((PACKAGE.joinpath(*parts)).rglob("*.py"))


@pytest.mark.parametrize("path", sources("contracts"), ids=str)
def test_contracts_have_no_web_or_model_frameworks(path):
    assert not imports(path) & (WEB | MODEL | DATABASE)


@pytest.mark.parametrize("path", sources("pipeline") + sources("ml"), ids=str)
def test_pipeline_and_ml_do_not_import_web_framework(path):
    assert not imports(path) & (WEB | DATABASE)


@pytest.mark.parametrize("path", sources(), ids=str)
def test_python_has_no_business_database_or_broker(path):
    assert not imports(path) & DATABASE
