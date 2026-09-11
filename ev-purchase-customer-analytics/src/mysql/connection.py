from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL, make_url


ROOT = Path(__file__).resolve().parents[2]
DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


class DatabaseConfigurationError(RuntimeError):
    """Raised when local MySQL connection settings are incomplete."""


@dataclass(frozen=True)
class MySQLSettings:
    host: str
    port: int
    user: str
    password: str
    database: str
    database_url: str | None = None

    def masked_summary(self) -> str:
        return f"mysql+pymysql://{self.user}:***@{self.host}:{self.port}/{self.database}"


def load_settings(database_override: str | None = None) -> MySQLSettings:
    load_dotenv(ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        url = make_url(database_url)
        if not url.drivername.startswith("mysql"):
            raise DatabaseConfigurationError("DATABASE_URL must use a MySQL driver.")
        settings = MySQLSettings(
            host=url.host or "127.0.0.1",
            port=int(url.port or 3306),
            user=url.username or "",
            password=url.password or "",
            database=url.database or "ev_customer_analytics",
            database_url=database_url,
        )
    else:
        settings = MySQLSettings(
            host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MYSQL_USER", ""),
            password=os.getenv("MYSQL_PASSWORD", ""),
            database=os.getenv("MYSQL_DATABASE", "ev_customer_analytics"),
        )
    if database_override:
        settings = replace(settings, database=database_override)
    if not settings.user or not settings.password:
        raise DatabaseConfigurationError(
            "MySQL credentials are missing. Copy .env.example to .env and set "
            "MYSQL_USER and MYSQL_PASSWORD, or provide DATABASE_URL."
        )
    if not DATABASE_NAME_PATTERN.fullmatch(settings.database):
        raise DatabaseConfigurationError("MYSQL_DATABASE may contain only letters, digits and underscores.")
    return settings


def _url(settings: MySQLSettings, include_database: bool) -> URL:
    return URL.create(
        drivername="mysql+pymysql",
        username=settings.user,
        password=settings.password,
        host=settings.host,
        port=settings.port,
        database=settings.database if include_database else None,
        query={"charset": "utf8mb4"},
    )


def create_server_engine(settings: MySQLSettings) -> Engine:
    return create_engine(_url(settings, include_database=False), pool_pre_ping=True, future=True)


def create_database_engine(settings: MySQLSettings) -> Engine:
    return create_engine(_url(settings, include_database=True), pool_pre_ping=True, future=True)


def ensure_database(settings: MySQLSettings) -> None:
    engine = create_server_engine(settings)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{settings.database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
                )
            )
    finally:
        engine.dispose()
