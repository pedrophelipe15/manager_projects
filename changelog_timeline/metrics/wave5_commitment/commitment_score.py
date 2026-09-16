"""Wave 5.2 — Commitment Score e agregacoes de leitura.

Funcoes on-read que agregam a tabela metrics_due_date_slippage (populada por
due_date_slippage.calculate_due_date_slippage) em respostas prontas para a API.

Commitment score = % de issues (com prazo definido) entregues sem nenhuma
reprogramacao. Quanto maior, mais confiavel o compromisso de prazo do time.
"""

from __future__ import annotations

import sqlite3

# Ordem de severidade para ranquear os piores primeiro.
_CLASS_RANK = {"pushing": 0, "attention": 1, "replanned": 2, "kept": 3}

_CLASS_LABEL = {
    "kept": "Compromisso mantido",
    "replanned": "Replanejamento normal",
    "attention": "Atencao",
    "pushing": "Prazo sendo empurrado",
}


def _summarize(rows: list[dict]) -> dict:
    """Monta contadores + commitment score a partir de uma lista de registros."""
    total = len(rows)
    counts = {"kept": 0, "replanned": 0, "attention": 0, "pushing": 0}
    total_pushes = 0
    total_days_pushed = 0
    for r in rows:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1
        total_pushes += r["pushes"]
        total_days_pushed += r["total_days_pushed"]

    kept = counts["kept"]
    commitment_score = round(100 * kept / total, 1) if total else 0.0

    return {
        "total_issues": total,
        "commitment_score": commitment_score,
        "counts": counts,
        "total_reschedules_pushes": total_pushes,
        "total_days_pushed": total_days_pushed,
    }


def get_slippage_by_project(conn: sqlite3.Connection, project_key: str) -> dict:
    """Slippage detalhado de um projeto: resumo + por assignee + issues piores."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT issue_key, project_key, assignee_name, reschedules, pushes, pulls,
               total_days_pushed, original_due, current_due, last_changed_at, classification
        FROM metrics_due_date_slippage
        WHERE project_key = ?
        """,
        (project_key,),
    )
    cols = [d[0] for d in cursor.description]
    rows = [dict(zip(cols, r)) for r in cursor.fetchall()]

    summary = _summarize(rows)

    # Agrega por assignee
    by_assignee: dict[str, list[dict]] = {}
    for r in rows:
        name = r["assignee_name"] or "Sem responsavel"
        by_assignee.setdefault(name, []).append(r)

    people = []
    for name, group in by_assignee.items():
        s = _summarize(group)
        people.append({
            "assignee": name,
            "total_issues": s["total_issues"],
            "commitment_score": s["commitment_score"],
            "counts": s["counts"],
            "total_days_pushed": s["total_days_pushed"],
        })
    # Pior compromisso primeiro (menor score, mais dias empurrados)
    people.sort(key=lambda p: (p["commitment_score"], -p["total_days_pushed"]))

    # Issues mais criticas (mais reprogramacoes / mais dias empurrados)
    worst = sorted(
        rows,
        key=lambda r: (_CLASS_RANK.get(r["classification"], 9), -r["reschedules"], -r["total_days_pushed"]),
    )
    worst_issues = [
        {
            "issue_key": r["issue_key"],
            "assignee": r["assignee_name"] or "Sem responsavel",
            "reschedules": r["reschedules"],
            "pushes": r["pushes"],
            "total_days_pushed": r["total_days_pushed"],
            "original_due": r["original_due"],
            "current_due": r["current_due"],
            "classification": r["classification"],
            "classification_label": _CLASS_LABEL.get(r["classification"], r["classification"]),
        }
        for r in worst
        if r["reschedules"] > 0
    ][:100]

    return {
        "project_key": project_key,
        "summary": summary,
        "by_assignee": people,
        "worst_issues": worst_issues,
    }


def get_commitment_summary_all(conn: sqlite3.Connection) -> dict:
    """Resumo de commitment por projeto (para a home 'Minha Visao')."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT project_key, classification, COUNT(1), COALESCE(SUM(total_days_pushed), 0)
        FROM metrics_due_date_slippage
        GROUP BY project_key, classification
        """
    )
    acc: dict[str, dict] = {}
    for project_key, classification, count, days in cursor.fetchall():
        p = acc.setdefault(
            project_key,
            {"project_key": project_key, "total_issues": 0,
             "counts": {"kept": 0, "replanned": 0, "attention": 0, "pushing": 0},
             "total_days_pushed": 0},
        )
        p["counts"][classification] = p["counts"].get(classification, 0) + count
        p["total_issues"] += count
        p["total_days_pushed"] += days

    projects = []
    for p in acc.values():
        total = p["total_issues"]
        p["commitment_score"] = round(100 * p["counts"]["kept"] / total, 1) if total else 0.0
        projects.append(p)
    projects.sort(key=lambda x: x["commitment_score"])

    return {"projects": projects}
