"""Wave 1.4 — Cumulative Flow Diagram (CFD).
Gera snapshot diário: quantas issues estavam em cada status por dia.
Persiste na tabela metrics_cfd.

Algoritmo O(N+T): varredura incremental em vez de triple-loop.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict

from ..changelog_cache import StatusTransitions


def setup_table(conn: sqlite3.Connection):
    """Cria tabela metrics_cfd se não existir."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS metrics_cfd (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_key TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            status TEXT NOT NULL,
            count INTEGER NOT NULL,
            UNIQUE(project_key, snapshot_date, status)
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_cfd_project_date ON metrics_cfd(project_key, snapshot_date)')
    conn.commit()


def calculate_cfd(
    conn: sqlite3.Connection,
    only_keys: list[str] | None = None,
    status_cache: dict[str, StatusTransitions] | None = None,
) -> int:
    """Calcula CFD (snapshots diários de contagem por status) por projeto.
    
    Algoritmo incremental O(N+T):
    1. Coleta todos os eventos (criação + transições) e ordena por data
    2. Varre eventos em ordem, mantendo contadores correntes por status
    3. Quando cruza a fronteira de um dia, persiste o snapshot

    Se only_keys for fornecido, recalcula apenas para os projetos dessas issues,
    mas usa TODAS as issues do projeto para gerar o CFD correto.
    
    Retorna quantidade de registros persistidos.
    """
    setup_table(conn)
    cursor = conn.cursor()

    # Determina projetos afetados
    if only_keys:
        placeholders = ",".join(["?" for _ in only_keys])
        cursor.execute(f"SELECT DISTINCT project_key FROM issues WHERE key IN ({placeholders})", only_keys)
    else:
        cursor.execute("SELECT DISTINCT project_key FROM issues")
    projects = [r[0] for r in cursor.fetchall()]

    now = datetime.now()
    start_date = (now - timedelta(days=90)).replace(hour=0, minute=0, second=0, microsecond=0)
    all_rows: list[tuple] = []

    for project_key in projects:
        # Remove dados antigos deste projeto
        cursor.execute("DELETE FROM metrics_cfd WHERE project_key = ?", (project_key,))

        # Coleta eventos: (datetime, issue_key, tipo, status)
        # tipo: 'enter' = issue entra neste status, 'leave' = issue sai deste status
        events: list[tuple[datetime, str, str, str]] = []

        # 1. Issues criadas — cada uma entra em "Open" na data de criação
        cursor.execute("SELECT key, created_at FROM issues WHERE project_key = ?", (project_key,))
        issues_created = cursor.fetchall()

        for issue_key, created_at in issues_created:
            if not created_at:
                continue
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")).replace(tzinfo=None)
                events.append((dt, issue_key, "enter", "Open"))
            except (ValueError, TypeError):
                continue

        # 2. Transições de status — cada uma gera leave(from) + enter(to)
        if status_cache is not None:
            # Filtra cache para issues deste projeto
            project_issue_keys = {row[0] for row in issues_created}
            for issue_key in project_issue_keys:
                transitions = status_cache.get(issue_key, [])
                for event_date_str, from_value, to_value in transitions:
                    if not event_date_str:
                        continue
                    try:
                        dt = datetime.fromisoformat(event_date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    except (ValueError, TypeError):
                        continue
                    if from_value:
                        events.append((dt, issue_key, "leave", from_value))
                    if to_value:
                        events.append((dt, issue_key, "enter", to_value))
        else:
            cursor.execute('''
                SELECT pc.issue_key, pc.event_date, pc.from_value, pc.to_value
                FROM parsed_changelogs pc
                INNER JOIN issues i ON pc.issue_key = i.key
                WHERE pc.field = 'status' AND i.project_key = ?
                ORDER BY pc.event_date ASC
            ''', (project_key,))
            for issue_key, event_date_str, from_value, to_value in cursor.fetchall():
                if not event_date_str:
                    continue
                try:
                    dt = datetime.fromisoformat(event_date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                except (ValueError, TypeError):
                    continue
                if from_value:
                    events.append((dt, issue_key, "leave", from_value))
                if to_value:
                    events.append((dt, issue_key, "enter", to_value))

        # Ordena eventos cronologicamente
        events.sort(key=lambda e: e[0])

        # Varredura incremental: mantém contadores correntes por status
        status_counts: dict[str, int] = defaultdict(int)
        event_idx = 0
        total_events = len(events)

        # Gera snapshots para cada dia no período de 90 dias
        current_date = start_date
        end_of_day = current_date.replace(hour=23, minute=59, second=59)

        while current_date <= now:
            # Processa todos os eventos até o final deste dia
            while event_idx < total_events and events[event_idx][0] <= end_of_day:
                _, _, event_type, status = events[event_idx]
                if event_type == "enter":
                    status_counts[status] += 1
                else:  # leave
                    status_counts[status] = max(0, status_counts[status] - 1)
                event_idx += 1

            # Persiste snapshot do dia (só se há dados)
            date_str = current_date.strftime("%Y-%m-%d")
            for status, cnt in status_counts.items():
                if cnt > 0:
                    all_rows.append((project_key, date_str, status, cnt))

            # Avança para o próximo dia
            current_date += timedelta(days=1)
            end_of_day = current_date.replace(hour=23, minute=59, second=59)

    # Batch insert com executemany
    if all_rows:
        cursor.executemany('''
            INSERT OR REPLACE INTO metrics_cfd (project_key, snapshot_date, status, count)
            VALUES (?, ?, ?, ?)
        ''', all_rows)

    conn.commit()
    return len(all_rows)
