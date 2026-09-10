"""Wave 1.1 — Tempo médio/P85 por status (gargalo direto).
Calcula quanto tempo cada issue ficou em cada status e persiste na tabela metrics_per_status.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ..changelog_cache import StatusTransitions


def setup_table(conn: sqlite3.Connection):
    """Cria tabela metrics_per_status se não existir."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS metrics_per_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_key TEXT NOT NULL,
            project_key TEXT NOT NULL,
            status TEXT NOT NULL,
            duration_ms INTEGER NOT NULL,
            entered_at TEXT,
            exited_at TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_mps_project ON metrics_per_status(project_key)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_mps_issue ON metrics_per_status(issue_key)')
    conn.commit()


def calculate_time_per_status(
    conn: sqlite3.Connection,
    only_keys: list[str] | None = None,
    status_cache: dict[str, StatusTransitions] | None = None,
) -> int:
    """Calcula tempo por status para cada issue e persiste.
    
    Se status_cache for fornecido, usa os dados pré-carregados.
    Retorna quantidade de intervalos calculados.
    """
    setup_table(conn)
    cursor = conn.cursor()

    # Busca issues alvo
    if only_keys:
        placeholders = ",".join(["?" for _ in only_keys])
        cursor.execute(f"SELECT key, project_key, created_at FROM issues WHERE key IN ({placeholders})", only_keys)
    else:
        cursor.execute("SELECT key, project_key, created_at FROM issues")
    issues = cursor.fetchall()

    # Batch delete de registros antigos
    if only_keys:
        for i in range(0, len(only_keys), 500):
            batch = only_keys[i:i + 500]
            ph = ",".join(["?" for _ in batch])
            cursor.execute(f"DELETE FROM metrics_per_status WHERE issue_key IN ({ph})", batch)
    else:
        cursor.execute("DELETE FROM metrics_per_status")

    # Calcula todos os intervalos e acumula para executemany
    all_rows: list[tuple] = []

    for issue_key, project_key, created_at in issues:
        # Busca transições de status
        if status_cache is not None:
            transitions = status_cache.get(issue_key, [])
        else:
            cursor.execute('''
                SELECT event_date, from_value, to_value
                FROM parsed_changelogs
                WHERE issue_key = ? AND field = 'status'
                ORDER BY event_date ASC
            ''', (issue_key,))
            transitions = cursor.fetchall()

        if not transitions:
            continue

        # O primeiro registro indica: saiu de from_value, entrou em to_value
        prev_status = transitions[0][1]  # from_value do primeiro evento
        prev_date = None

        # Usa created_at como data de entrada no primeiro status
        if created_at:
            try:
                prev_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                prev_date = None

        for event_date_str, from_value, to_value in transitions:
            if not event_date_str:
                continue
            try:
                event_dt = datetime.fromisoformat(event_date_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            # Registra tempo no status anterior
            if prev_status and prev_date:
                duration_ms = int((event_dt - prev_date).total_seconds() * 1000)
                if duration_ms > 0:
                    all_rows.append((
                        issue_key, project_key, prev_status, duration_ms,
                        prev_date.isoformat(), event_dt.isoformat()
                    ))

            prev_status = to_value
            prev_date = event_dt

        # Status atual (sem saída) — registra até agora para issues ativas
        if prev_status and prev_date:
            now = datetime.now(prev_date.tzinfo) if prev_date.tzinfo else datetime.now()
            duration_ms = int((now - prev_date).total_seconds() * 1000)
            if duration_ms > 0:
                all_rows.append((
                    issue_key, project_key, prev_status, duration_ms,
                    prev_date.isoformat(), None
                ))

    # Batch insert com executemany
    if all_rows:
        cursor.executemany('''
            INSERT INTO metrics_per_status (issue_key, project_key, status, duration_ms, entered_at, exited_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', all_rows)

    conn.commit()
    return len(all_rows)
