from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import Engine


def _statements(path: Path) -> list[str]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("--")]
    return [statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()]


def create_schema(engine: Engine, sql_dir: Path) -> None:
    with engine.begin() as connection:
        for statement in _statements(sql_dir / "01_schema.sql"):
            connection.exec_driver_sql(statement)
