"""Migrações versionadas por banco (cada módulo tem a sua pasta `migrations/`).

Convenção: arquivos `NNN_descricao.sql` ou `NNN_descricao.py` (com `upgrade(conn)`),
aplicados em ordem numérica e registrados na tabela `schema_version` do PRÓPRIO banco.

Propriedades:
  - idempotente: rodar de novo não altera nada;
  - serve para instalação nova E para banco já existente (a migração 001 usa
    CREATE ... IF NOT EXISTS, então um banco legado só ganha o registro de versão);
  - o banco (.db) nunca vai para o git: só estas migrações.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sqlite3
from datetime import datetime, timezone

_NAME = re.compile(r"^(\d{3,})_([\w\-]+)\.(sql|py)$")


def discover(migrations_dir: str) -> list[tuple[int, str, str]]:
    """Retorna [(versão, nome, caminho)] ordenado; erro se houver versão duplicada."""
    found: dict[int, tuple[int, str, str]] = {}
    for fname in sorted(os.listdir(migrations_dir)):
        m = _NAME.match(fname)
        if not m:
            continue
        version = int(m.group(1))
        if version in found:
            raise ValueError(f"versão de migração duplicada: {version} em {migrations_dir}")
        found[version] = (version, f"{m.group(1)}_{m.group(2)}", os.path.join(migrations_dir, fname))
    return [found[v] for v in sorted(found)]


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    conn.commit()


def current_version(conn: sqlite3.Connection) -> int:
    _ensure_version_table(conn)
    row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()
    return int(row[0])


def read_version(db_path: str) -> int | None:
    """Versão do schema de um banco, sem criar nada. None se o arquivo/tabela não existe."""
    if not os.path.exists(db_path):
        return None
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return int(row[0]) if row and row[0] is not None else None
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


def _load_py(path: str):
    spec = importlib.util.spec_from_file_location(f"_migration_{os.path.basename(path)[:-3]}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def apply_migrations(conn: sqlite3.Connection, migrations_dir: str) -> list[str]:
    """Aplica as migrações pendentes. Retorna os nomes aplicados nesta chamada."""
    _ensure_version_table(conn)
    done = {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    applied: list[str] = []
    for version, name, path in discover(migrations_dir):
        if version in done:
            continue
        if path.endswith(".sql"):
            with open(path, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
        else:
            _load_py(path).upgrade(conn)
        conn.execute(
            "INSERT OR IGNORE INTO schema_version (version, name, applied_at) VALUES (?, ?, ?)",
            (version, name, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()
        applied.append(name)
    return applied


def migrate_db(db_path: str, migrations_dir: str) -> list[str]:
    """Abre o banco (criando o arquivo se preciso), aplica as migrações e fecha."""
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        return apply_migrations(conn, migrations_dir)
    finally:
        conn.close()


def add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, ddl_type: str) -> bool:
    """ALTER TABLE ... ADD COLUMN só se a coluna ainda não existe (bancos legados)."""
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info('{table}')")}
    if column in cols:
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
    return True
