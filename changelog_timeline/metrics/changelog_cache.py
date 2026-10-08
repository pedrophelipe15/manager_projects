"""Cache compartilhado de changelogs de status.

Carrega uma vez do banco e distribui para todos os módulos de métricas,
eliminando N+1 queries redundantes (base, time_per_status, flow_efficiency).
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any


# Tipo: lista de (event_date, from_value, to_value) ordenada cronologicamente
StatusTransitions = list[tuple[str, str | None, str | None]]


def load_status_changelogs(
    conn: sqlite3.Connection,
    only_keys: list[str] | None = None,
) -> dict[str, StatusTransitions]:
    """Carrega todas as transições de status em uma única query.
    
    Retorna dict[issue_key] -> [(event_date, from_value, to_value), ...] ordenado por event_date.
    
    Se only_keys for fornecido, carrega apenas para essas issues.
    Caso contrário, carrega todas as transições do banco.
    """
    cursor = conn.cursor()

    if only_keys:
        # Batch em chunks de 500 para evitar limite de variáveis do SQLite
        result: dict[str, StatusTransitions] = defaultdict(list)
        for i in range(0, len(only_keys), 500):
            batch = only_keys[i:i + 500]
            placeholders = ",".join(["?" for _ in batch])
            cursor.execute(f"""
                SELECT issue_key, event_date, from_value, to_value
                FROM parsed_changelogs
                WHERE field = 'status' AND issue_key IN ({placeholders})
                ORDER BY issue_key, event_date ASC
            """, batch)
            for row in cursor.fetchall():
                result[row[0]].append((row[1], row[2], row[3]))
        return dict(result)
    else:
        cursor.execute("""
            SELECT issue_key, event_date, from_value, to_value
            FROM parsed_changelogs
            WHERE field = 'status'
            ORDER BY issue_key, event_date ASC
        """)
        result: dict[str, StatusTransitions] = defaultdict(list)
        for row in cursor.fetchall():
            result[row[0]].append((row[1], row[2], row[3]))
        return dict(result)
