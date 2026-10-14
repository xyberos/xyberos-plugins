"""Database plugin (RFC-0019/0020, M9)."""

from .adapters import DuckdbDatabase, MysqlDatabase, PostgresDatabase, SqliteDatabase, build_database
from .contract import Database
from .plugin import DbPlugin

__all__ = [
    "Database",
    "DbPlugin",
    "DuckdbDatabase",
    "MysqlDatabase",
    "PostgresDatabase",
    "SqliteDatabase",
    "build_database",
]
