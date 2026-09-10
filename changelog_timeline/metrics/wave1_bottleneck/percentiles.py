"""Wave 1.2 — Percentis de Lead Time e Cycle Time.
Calcula P50, P70, P85, P95 por projeto e persiste na tabela metrics_percentiles.
Não precisa de tabela granular — agrega da tabela metrics existente.
"""

from __future__ import annotations

import sqlite3
import math


def setup_table(conn: sqlite3.Connection):
    """Cria tabela metrics_percentiles se não existir."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS metrics_percentiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_key TEXT NOT NULL,
            metric_type TEXT NOT NULL,
            p50_ms INTEGER,
            p70_ms INTEGER,
            p85_ms INTEGER,
            p95_ms INTEGER,
            avg_ms INTEGER,
            count INTEGER,
            UNIQUE(project_key, metric_type)
        )
    ''')
    conn.commit()


def _percentile(sorted_values: list[int], pct: float) -> int:
    """Calcula percentil de uma lista já ordenada."""
    if not sorted_values:
        return 0
    idx = int(math.ceil(pct / 100.0 * len(sorted_values))) - 1
    idx = max(0, min(idx, len(sorted_values) - 1))
    return sorted_values[idx]


def calculate_percentiles(conn: sqlite3.Connection, only_keys: list[str] | None = None) -> int:
    """Calcula percentis de lead/cycle time por projeto.
    
    Retorna quantidade de registros persistidos.
    """
    setup_table(conn)
    cursor = conn.cursor()

    # Busca projetos distintos
    if only_keys:
        placeholders = ",".join(["?" for _ in only_keys])
        cursor.execute(f"SELECT DISTINCT project_key FROM issues WHERE key IN ({placeholders})", only_keys)
    else:
        cursor.execute("SELECT DISTINCT project_key FROM issues")
    projects = [r[0] for r in cursor.fetchall()]

    count = 0
    for project_key in projects:
        # Lead time (só Done com lead > 0)
        cursor.execute("""
            SELECT lead_time_ms FROM metrics 
            WHERE project_key = ? AND lead_time_ms > 0
            ORDER BY lead_time_ms
        """, (project_key,))
        lead_values = [r[0] for r in cursor.fetchall()]

        if lead_values:
            avg_lead = int(sum(lead_values) / len(lead_values))
            cursor.execute('''
                INSERT OR REPLACE INTO metrics_percentiles 
                (project_key, metric_type, p50_ms, p70_ms, p85_ms, p95_ms, avg_ms, count)
                VALUES (?, 'lead_time', ?, ?, ?, ?, ?, ?)
            ''', (
                project_key,
                _percentile(lead_values, 50),
                _percentile(lead_values, 70),
                _percentile(lead_values, 85),
                _percentile(lead_values, 95),
                avg_lead,
                len(lead_values),
            ))
            count += 1

        # Cycle time (só com cycle > 0)
        cursor.execute("""
            SELECT cycle_time_ms FROM metrics 
            WHERE project_key = ? AND cycle_time_ms > 0
            ORDER BY cycle_time_ms
        """, (project_key,))
        cycle_values = [r[0] for r in cursor.fetchall()]

        if cycle_values:
            avg_cycle = int(sum(cycle_values) / len(cycle_values))
            cursor.execute('''
                INSERT OR REPLACE INTO metrics_percentiles 
                (project_key, metric_type, p50_ms, p70_ms, p85_ms, p95_ms, avg_ms, count)
                VALUES (?, 'cycle_time', ?, ?, ?, ?, ?, ?)
            ''', (
                project_key,
                _percentile(cycle_values, 50),
                _percentile(cycle_values, 70),
                _percentile(cycle_values, 85),
                _percentile(cycle_values, 95),
                avg_cycle,
                len(cycle_values),
            ))
            count += 1

    conn.commit()
    return count
