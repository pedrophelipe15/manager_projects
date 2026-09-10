"""Métricas base: Lead Time e Cycle Time.
Fonte de verdade para as métricas fundamentais do projeto.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .changelog_cache import StatusTransitions
from .constants import ACTIVE_STATES


def calculate_metrics(
    conn: sqlite3.Connection,
    only_keys: list[str] | None = None,
    status_cache: dict[str, StatusTransitions] | None = None,
) -> int:
    """Calcula lead time e cycle time a partir dos changelogs e persiste na tabela metrics.
    
    Se only_keys for fornecido, recalcula apenas para essas issue keys.
    Se status_cache for fornecido, usa os dados pré-carregados em vez de queries individuais.
    """
    cursor = conn.cursor()

    if only_keys:
        placeholders = ",".join(["?" for _ in only_keys])
        cursor.execute(
            f"SELECT key, project_key, project_name, parent_key, status, created_at, updated_at, due_date, resolved_at FROM issues WHERE key IN ({placeholders})",
            only_keys
        )
    else:
        cursor.execute("SELECT key, project_key, project_name, parent_key, status, created_at, updated_at, due_date, resolved_at FROM issues")
    issues = cursor.fetchall()

    count = 0
    for issue in issues:
        key, project_key, project_name, parent_key, status, created_at, updated_at, due_date, resolved_at = issue

        # Lead time: created_at até resolved_at (em ms)
        lead_time_ms = 0
        if created_at and resolved_at:
            try:
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                resolved_dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
                lead_time_ms = int((resolved_dt - created_dt).total_seconds() * 1000)
            except (ValueError, TypeError):
                lead_time_ms = 0

        # Cycle time: soma dos intervalos em estados ativos
        if status_cache is not None:
            status_changes = status_cache.get(key, [])
        else:
            cursor.execute('''
                SELECT event_date, from_value, to_value 
                FROM parsed_changelogs 
                WHERE issue_key = ? AND field = 'status'
                ORDER BY event_date ASC
            ''', (key,))
            status_changes = cursor.fetchall()

        cycle_time_ms = 0
        active_start = None

        for event_date, from_value, to_value in status_changes:
            if not event_date:
                continue
            try:
                event_dt = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            if to_value in ACTIVE_STATES and active_start is None:
                active_start = event_dt

            if from_value in ACTIVE_STATES and to_value not in ACTIVE_STATES and active_start is not None:
                interval_ms = int((event_dt - active_start).total_seconds() * 1000)
                cycle_time_ms += interval_ms
                active_start = None

        # Intervalo aberto
        if active_start and status in ACTIVE_STATES:
            now = datetime.now(active_start.tzinfo) if active_start.tzinfo else datetime.now()
            interval_ms = int((now - active_start).total_seconds() * 1000)
            cycle_time_ms += interval_ms

        cursor.execute('''
            INSERT OR REPLACE INTO metrics 
            (issue_key, project_key, project_name, parent_key, status, 
             created_at, updated_at, due_date, resolved_at, lead_time_ms, cycle_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            key, project_key, project_name, parent_key, status,
            created_at, updated_at, due_date, resolved_at,
            lead_time_ms, cycle_time_ms,
        ))
        count += 1

    conn.commit()
    return count
