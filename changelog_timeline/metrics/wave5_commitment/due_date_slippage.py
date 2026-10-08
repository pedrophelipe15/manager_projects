"""Wave 5.1 — Due Date Slippage (Compromisso de Prazo).

Responde a pergunta nº1 dos gestores: "a equipe esta cumprindo prazo ou
so empurrando a data pra frente?".

Fonte: parsed_changelogs WHERE field='duedate'. Cada evento tem from_value
(data anterior) e to_value (data nova). Regras:

  - from_value NULL/vazio  -> primeira definicao de prazo (NAO conta como
    reprogramacao; e a data original prometida).
  - from_value e to_value preenchidos -> reprogramacao. Se to > from o prazo
    foi EMPURRADO pra frente (push); se to < from foi antecipado (pull).

Persiste um registro por issue em metrics_due_date_slippage.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime


def setup_table(conn: sqlite3.Connection):
    """Cria a tabela metrics_due_date_slippage se nao existir."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS metrics_due_date_slippage (
            issue_key TEXT PRIMARY KEY,
            project_key TEXT NOT NULL,
            assignee_name TEXT,
            reschedules INTEGER NOT NULL DEFAULT 0,
            pushes INTEGER NOT NULL DEFAULT 0,
            pulls INTEGER NOT NULL DEFAULT 0,
            total_days_pushed INTEGER NOT NULL DEFAULT 0,
            original_due TEXT,
            current_due TEXT,
            last_changed_at TEXT,
            classification TEXT NOT NULL DEFAULT 'kept'
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_slippage_project ON metrics_due_date_slippage(project_key)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_slippage_assignee ON metrics_due_date_slippage(assignee_name)')
    conn.commit()


def _parse_due(value: str | None) -> datetime | None:
    """Converte um valor de duedate do changelog ('2026-09-04 00:00:00.0' ou
    ISO) em datetime. Retorna None se vazio/invalido."""
    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    # Formato mais comum no changelog: '2026-09-04 00:00:00.0'
    v = v.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(v.split("+")[0].strip(), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(v)
    except (ValueError, TypeError):
        return None


def _classify(reschedules: int) -> str:
    """Classificacao proposta (validar com os gestores):
      0 -> kept        (compromisso mantido)
      1 -> replanned   (replanejamento normal)
      2 -> attention   (atencao)
      3+ -> pushing    (prazo sendo empurrado)
    """
    if reschedules <= 0:
        return "kept"
    if reschedules == 1:
        return "replanned"
    if reschedules == 2:
        return "attention"
    return "pushing"


def calculate_due_date_slippage(
    conn: sqlite3.Connection,
    only_keys: list[str] | None = None,
) -> int:
    """Calcula o slippage de prazo por issue e persiste.

    Considera apenas issues que existem na tabela issues (junta assignee/projeto).
    Retorna a quantidade de issues com pelo menos uma definicao de prazo.
    """
    setup_table(conn)
    cursor = conn.cursor()

    # Limpa registros orfaos (issues removidas do banco)
    cursor.execute(
        "DELETE FROM metrics_due_date_slippage WHERE issue_key NOT IN (SELECT key FROM issues)"
    )

    # Escopo de issues alvo
    if only_keys:
        target_keys = only_keys
        for i in range(0, len(target_keys), 500):
            batch = target_keys[i:i + 500]
            ph = ",".join(["?" for _ in batch])
            cursor.execute(
                f"DELETE FROM metrics_due_date_slippage WHERE issue_key IN ({ph})", batch
            )
    else:
        cursor.execute("DELETE FROM metrics_due_date_slippage")
        target_keys = None

    # Metadados das issues (projeto + assignee)
    meta: dict[str, tuple[str, str | None]] = {}
    if target_keys:
        for i in range(0, len(target_keys), 500):
            batch = target_keys[i:i + 500]
            ph = ",".join(["?" for _ in batch])
            cursor.execute(
                f"SELECT key, project_key, assignee_name FROM issues WHERE key IN ({ph})",
                batch,
            )
            for k, pk, an in cursor.fetchall():
                meta[k] = (pk, an)
    else:
        cursor.execute("SELECT key, project_key, assignee_name FROM issues")
        for k, pk, an in cursor.fetchall():
            meta[k] = (pk, an)

    if not meta:
        conn.commit()
        return 0

    # Eventos de duedate das issues alvo, em ordem cronologica
    keys = list(meta.keys())
    events: dict[str, list[tuple[str, str | None, str | None]]] = {}
    for i in range(0, len(keys), 500):
        batch = keys[i:i + 500]
        ph = ",".join(["?" for _ in batch])
        cursor.execute(
            f"""
            SELECT issue_key, event_date, from_value, to_value
            FROM parsed_changelogs
            WHERE field = 'duedate' AND issue_key IN ({ph})
            ORDER BY issue_key, event_date ASC
            """,
            batch,
        )
        for issue_key, event_date, from_value, to_value in cursor.fetchall():
            events.setdefault(issue_key, []).append((event_date, from_value, to_value))

    rows: list[tuple] = []
    for issue_key, evs in events.items():
        project_key, assignee_name = meta.get(issue_key, (None, None))
        if project_key is None:
            continue

        reschedules = 0
        pushes = 0
        pulls = 0
        total_days_pushed = 0
        original_due: datetime | None = None
        current_due: datetime | None = None
        last_changed_at: str | None = None

        for event_date, from_value, to_value in evs:
            from_dt = _parse_due(from_value)
            to_dt = _parse_due(to_value)

            # data original = primeira data conhecida (from do 1o evento, ou to)
            if original_due is None:
                original_due = from_dt or to_dt
            if to_dt is not None:
                current_due = to_dt
            if event_date:
                last_changed_at = event_date

            # reprogramacao real: tinha data antes e mudou para outra data
            if from_dt is not None and to_dt is not None and from_dt != to_dt:
                reschedules += 1
                delta_days = (to_dt - from_dt).days
                if delta_days > 0:
                    pushes += 1
                    total_days_pushed += delta_days
                elif delta_days < 0:
                    pulls += 1

        rows.append((
            issue_key,
            project_key,
            assignee_name,
            reschedules,
            pushes,
            pulls,
            total_days_pushed,
            original_due.date().isoformat() if original_due else None,
            current_due.date().isoformat() if current_due else None,
            last_changed_at,
            _classify(reschedules),
        ))

    if rows:
        cursor.executemany('''
            INSERT OR REPLACE INTO metrics_due_date_slippage
            (issue_key, project_key, assignee_name, reschedules, pushes, pulls,
             total_days_pushed, original_due, current_due, last_changed_at, classification)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', rows)

    conn.commit()
    return len(rows)
