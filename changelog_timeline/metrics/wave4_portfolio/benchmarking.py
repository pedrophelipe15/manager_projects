"""Wave 4.2 — Benchmarking normalizado entre projetos.
Compara métricas de lead/cycle time e throughput entre projetos.
Não é para ranquear — é para identificar práticas melhores e replicar.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from ..constants import is_backward_transition


def get_benchmarking(conn: sqlite3.Connection) -> dict:
    """Retorna comparação de métricas entre todos os projetos.
    
    Para cada projeto calcula:
    - Lead Time P50/P85
    - Cycle Time P50/P85
    - Throughput médio semanal
    - Flow Efficiency média
    - Rework rate
    """
    cursor = conn.cursor()

    # Busca todos os projetos com dados
    cursor.execute("SELECT DISTINCT project_key FROM issues WHERE project_key IS NOT NULL")
    projects = [row[0] for row in cursor.fetchall()]

    if not projects:
        return {"projects": [], "summary": {}}

    results = []
    for project_key in projects:
        metrics = _get_project_metrics(conn, project_key)
        if metrics:
            results.append(metrics)

    # Ordena por cycle time P85 (menor = melhor fluxo)
    results.sort(key=lambda x: x.get("cycle_time_p85_ms", 0))

    return {"projects": results}


def _get_project_metrics(conn: sqlite3.Connection, project_key: str) -> dict | None:
    """Coleta métricas agregadas de um projeto para benchmarking."""
    cursor = conn.cursor()

    # Lead/Cycle time percentis
    cursor.execute("""
        SELECT metric_type, p50_ms, p85_ms, count
        FROM metrics_percentiles
        WHERE project_key = ?
    """, (project_key,))
    percentile_rows = cursor.fetchall()

    if not percentile_rows:
        return None

    lead_p50 = lead_p85 = cycle_p50 = cycle_p85 = 0
    lead_count = cycle_count = 0
    for row in percentile_rows:
        if row[0] == "lead_time":
            lead_p50, lead_p85, lead_count = row[1], row[2], row[3]
        elif row[0] == "cycle_time":
            cycle_p50, cycle_p85, cycle_count = row[1], row[2], row[3]

    # Throughput médio (últimas 12 semanas)
    cutoff = (datetime.now() - timedelta(weeks=12)).isoformat()
    cursor.execute('''
        SELECT COUNT(*) FROM issues
        WHERE project_key = ? AND status = 'Done'
          AND resolved_at IS NOT NULL AND resolved_at >= ?
    ''', (project_key, cutoff))
    done_12w = cursor.fetchone()[0]
    throughput_avg = round(done_12w / 12, 1)

    # Flow efficiency média
    cursor.execute("""
        SELECT AVG(flow_efficiency) FROM metrics_flow WHERE project_key = ?
    """, (project_key,))
    row = cursor.fetchone()
    flow_eff = round(row[0], 1) if row and row[0] else 0

    # Rework rate
    cursor.execute('''
        SELECT COUNT(DISTINCT pc.issue_key)
        FROM parsed_changelogs pc
        INNER JOIN issues i ON pc.issue_key = i.key
        WHERE i.project_key = ? AND pc.field = 'status'
    ''', (project_key,))
    total_issues_with_transitions = cursor.fetchone()[0]

    # Simplified rework: count issues with any backward transition
    cursor.execute('''
        SELECT pc.issue_key, pc.from_value, pc.to_value
        FROM parsed_changelogs pc
        INNER JOIN issues i ON pc.issue_key = i.key
        WHERE i.project_key = ? AND pc.field = 'status'
    ''', (project_key,))
    rework_issues = set()
    for issue_key, from_val, to_val in cursor.fetchall():
        if is_backward_transition(from_val, to_val):
            rework_issues.add(issue_key)

    rework_rate = round(len(rework_issues) / total_issues_with_transitions * 100, 1) if total_issues_with_transitions > 0 else 0

    # Total de issues ativas
    cursor.execute("SELECT COUNT(*) FROM issues WHERE project_key = ? AND status != 'Done'", (project_key,))
    active_count = cursor.fetchone()[0]

    return {
        "project_key": project_key,
        "lead_time_p50_ms": lead_p50,
        "lead_time_p85_ms": lead_p85,
        "cycle_time_p50_ms": cycle_p50,
        "cycle_time_p85_ms": cycle_p85,
        "lead_count": lead_count,
        "cycle_count": cycle_count,
        "throughput_avg_weekly": throughput_avg,
        "flow_efficiency_avg": flow_eff,
        "rework_rate_pct": rework_rate,
        "active_issues": active_count,
    }
