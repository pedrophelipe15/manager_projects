"""Descreve o schema de um banco SQLite de forma comparável (independe do texto do DDL)."""
import sqlite3

IGNORED_TABLES = {"schema_version"}


def dump_schema(db_path_or_conn) -> dict:
    conn = db_path_or_conn if isinstance(db_path_or_conn, sqlite3.Connection) else sqlite3.connect(db_path_or_conn)
    out = {}
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for t in tables:
        if t in IGNORED_TABLES:
            continue
        cols = [[r[1], r[2], r[3], r[4], r[5]] for r in conn.execute(f"PRAGMA table_info('{t}')")]
        idx = []
        for r in conn.execute(f"PRAGMA index_list('{t}')"):
            name, unique = r[1], r[2]
            icols = [c[2] for c in conn.execute(f"PRAGMA index_info('{name}')")]
            # índices automáticos (UNIQUE/PK) têm nome gerado: normaliza pelo conteúdo
            idx.append([("auto" if name.startswith("sqlite_autoindex") else name), unique, icols])
        fks = sorted([r[2], r[3], r[4]] for r in conn.execute(f"PRAGMA foreign_key_list('{t}')"))
        out[t] = {"columns": cols, "indexes": sorted(idx, key=lambda x: (x[0], x[2])), "fks": fks}
    return out
