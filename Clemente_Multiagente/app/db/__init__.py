"""Shared Postgres access: connection pool, migrations and per-table repositories."""

from .connection import connection

__all__ = ["connection"]
