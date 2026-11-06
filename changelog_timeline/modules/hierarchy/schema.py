"""Schema do banco do módulo HIERARCHY (hierarchy.db): aplica as migrações versionadas."""
from __future__ import annotations

import os

from kernel.migrations import migrate_db

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")


def migrate_hierarchy(db_path: str | None = None) -> list[str]:
    """Cria/atualiza o hierarchy.db. Chamado no on_enable do módulo e pelo exporter (CLI)."""
    if db_path is None:
        from hierarchy_db import HIERARCHY_DB_PATH
        db_path = HIERARCHY_DB_PATH
    return migrate_db(db_path, MIGRATIONS_DIR)
