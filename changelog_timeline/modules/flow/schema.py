"""Schema do banco do módulo FLOW (issues.db): aplica as migrações versionadas."""
from __future__ import annotations

import os
import sqlite3

from kernel.migrations import apply_migrations, migrate_db

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")


def ensure_flow_schema(conn: sqlite3.Connection) -> list[str]:
    """Garante o schema do flow na conexão dada (idempotente; usado por CLIs e métricas)."""
    return apply_migrations(conn, MIGRATIONS_DIR)


def migrate_flow(db_path: str | None = None) -> list[str]:
    """Cria/atualiza o issues.db. Chamado no on_enable do módulo."""
    if db_path is None:
        from modules.flow.db import DB_PATH
        db_path = DB_PATH
    return migrate_db(db_path, MIGRATIONS_DIR)
