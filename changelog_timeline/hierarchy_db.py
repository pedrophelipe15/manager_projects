"""Gerenciamento do banco hierarchy.db — isolado do issues.db.

Cria e gerencia o schema para a pipeline hierárquica (Iniciativas, Épicos, Stories, Sub-tasks).
"""

from __future__ import annotations

import os
import sqlite3

# MANAGER_HIERARCHY_DB_PATH permite apontar para outro banco (ex.: testes); default inalterado.
HIERARCHY_DB_PATH = os.environ.get("MANAGER_HIERARCHY_DB_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "hierarchy.db"
)


def get_hierarchy_connection() -> sqlite3.Connection:
    """Retorna conexão ao hierarchy.db com WAL e row_factory."""
    conn = sqlite3.connect(HIERARCHY_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def setup_hierarchy_db():
    """Cria/atualiza o hierarchy.db via migrações versionadas (modules/hierarchy/migrations).

    Não roda mais ao importar este módulo: é chamado no on_enable do módulo
    hierarchy e pelo exporter (CLI).
    """
    from modules.hierarchy.schema import migrate_hierarchy
    return migrate_hierarchy(HIERARCHY_DB_PATH)
