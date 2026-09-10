"""Métricas hierárquicas: Lead Time e Cycle Time para stories e subtasks do hierarchy.db.

Replica a lógica do metrics/base.py mas opera exclusivamente sobre o hierarchy.db,
lendo h_changelogs e persistindo em h_metrics.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime

import yaml


# Estados considerados "ativos" (issue está sendo trabalhada)
ACTIVE_STATES = {"In Progress", "Blocked", "Test", "Waiting for Delivery"}

# Estados considerados "concluídos" (issue finalizada)
DONE_STATES = {"Done", "Canceled"}

# Caminho do projects.yaml (fonte da lista de projetos excluídos)
_PROJECTS_YAML = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects.yaml"
)


def get_excluded_projects() -> list[str]:
    """Retorna os project_keys excluídos (uppercase) definidos em projects.yaml.

    Projetos excluídos não devem ser consolidados nos cálculos nem exibidos.
    O project_key é o prefixo da issue key antes do último hífen (ex: 'PSDC'
    em 'PSDC-1404').
    """
    if not os.path.exists(_PROJECTS_YAML):
        return []
    try:
        with open(_PROJECTS_YAML, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return []
    raw = data.get("excluded_projects", []) or []
    return [str(k).strip().upper() for k in raw if str(k).strip()]


def _project_key_from_issue_key(issue_key: str | None) -> str:
    """Deriva o project_key a partir da issue key (prefixo antes do último hífen)."""
    if not issue_key:
        return ""
    return issue_key.rsplit("-", 1)[0].upper() if "-" in issue_key else issue_key.upper()


def _excluded_where_clause(column: str = "project_key", excluded: list[str] | None = None):
    """Monta um trecho SQL (clause, params) que exclui os projetos informados.

    Retorna ("", []) quando não há projetos excluídos. A clause NÃO inclui
    prefixo 'AND'/'WHERE' — o chamador decide como combinar.
    """
    excluded = excluded if excluded is not None else get_excluded_projects()
    if not excluded:
        return "", []
    placeholders = ",".join(["?"] * len(excluded))
    # Compara em uppercase para robustez
    clause = f"(UPPER({column}) NOT IN ({placeholders}) OR {column} IS NULL)"
    return clause, list(excluded)


def _build_status_cache(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
    """Pré-carrega todas as transições de status do h_changelogs em memória.
    
    Retorna dict: issue_key → [(event_date, from_value, to_value), ...]
    ordenado por event_date ASC.
    """
    cursor = conn.cursor()
    cursor.execute('''
        SELECT issue_key, event_date, from_value, to_value
        FROM h_changelogs
        WHERE field = 'status'
        ORDER BY issue_key, event_date ASC
    ''')

    cache: dict[str, list[tuple]] = {}
    for row in cursor.fetchall():
        key = row["issue_key"]
        cache.setdefault(key, []).append((row["event_date"], row["from_value"], row["to_value"]))

    return cache


def _calc_lead_time_ms(created_at: str | None, resolved_at: str | None) -> int:
    """Lead time: created_at até resolved_at (em ms). Retorna 0 se dados ausentes."""
    if not created_at or not resolved_at:
        return 0
    try:
        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        resolved_dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
        return max(0, int((resolved_dt - created_dt).total_seconds() * 1000))
    except (ValueError, TypeError):
        return 0


def _calc_cycle_time_ms(
    status_changes: list[tuple],
    current_status: str | None,
) -> int:
    """Cycle time: soma dos intervalos em estados ativos (em ms).
    
    Se a issue está atualmente em estado ativo (intervalo aberto), 
    conta até datetime.now().
    """
    cycle_time_ms = 0
    active_start = None

    for event_date, from_value, to_value in status_changes:
        if not event_date:
            continue
        try:
            event_dt = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

        # Entrou em estado ativo
        if to_value in ACTIVE_STATES and active_start is None:
            active_start = event_dt

        # Saiu de estado ativo
        if from_value in ACTIVE_STATES and to_value not in ACTIVE_STATES and active_start is not None:
            interval_ms = int((event_dt - active_start).total_seconds() * 1000)
            cycle_time_ms += interval_ms
            active_start = None

    # Intervalo aberto: issue ainda está em estado ativo
    if active_start and current_status in ACTIVE_STATES:
        now = datetime.now(active_start.tzinfo) if active_start.tzinfo else datetime.now()
        interval_ms = int((now - active_start).total_seconds() * 1000)
        cycle_time_ms += interval_ms

    return cycle_time_ms


def calculate_hierarchy_metrics(conn: sqlite3.Connection) -> int:
    """Calcula lead time e cycle time para todas as stories e subtasks do hierarchy.db.
    
    Lê h_stories + h_subtasks, consulta h_changelogs, e persiste em h_metrics.
    Retorna o total de registros processados.
    """
    cursor = conn.cursor()

    # Pré-carrega cache de transições de status (evita N+1 queries)
    status_cache = _build_status_cache(conn)

    count = 0

    # Processa stories
    cursor.execute('''
        SELECT key, parent_key, project_key, status, created_at, resolved_at
        FROM h_stories
    ''')
    stories = cursor.fetchall()

    for row in stories:
        key = row["key"]
        parent_key = row["parent_key"]
        project_key = row["project_key"]
        status = row["status"]
        created_at = row["created_at"]
        resolved_at = row["resolved_at"]

        lead_time_ms = _calc_lead_time_ms(created_at, resolved_at)
        changes = status_cache.get(key, [])
        cycle_time_ms = _calc_cycle_time_ms(changes, status)

        cursor.execute('''
            INSERT OR REPLACE INTO h_metrics (issue_key, parent_key, project_key, status, lead_time_ms, cycle_time_ms)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (key, parent_key, project_key, status, lead_time_ms, cycle_time_ms))
        count += 1

    # Processa subtasks
    cursor.execute('''
        SELECT key, parent_key, project_key, status, created_at, resolved_at
        FROM h_subtasks
    ''')
    subtasks = cursor.fetchall()

    for row in subtasks:
        key = row["key"]
        parent_key = row["parent_key"]
        project_key = row["project_key"]
        status = row["status"]
        created_at = row["created_at"]
        resolved_at = row["resolved_at"]

        lead_time_ms = _calc_lead_time_ms(created_at, resolved_at)
        changes = status_cache.get(key, [])
        cycle_time_ms = _calc_cycle_time_ms(changes, status)

        cursor.execute('''
            INSERT OR REPLACE INTO h_metrics (issue_key, parent_key, project_key, status, lead_time_ms, cycle_time_ms)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (key, parent_key, project_key, status, lead_time_ms, cycle_time_ms))
        count += 1

    conn.commit()
    return count


def recalculate_hierarchy_metrics_for_keys(
    conn: sqlite3.Connection,
    issue_keys: list[str],
) -> int:
    """Recalcula métricas apenas para um subconjunto de issue keys.
    
    Útil após sync incremental.
    """
    if not issue_keys:
        return 0

    status_cache = _build_status_cache(conn)
    cursor = conn.cursor()
    count = 0

    placeholders = ",".join(["?" for _ in issue_keys])

    # Stories
    cursor.execute(
        f"SELECT key, parent_key, project_key, status, created_at, resolved_at FROM h_stories WHERE key IN ({placeholders})",
        issue_keys,
    )
    for row in cursor.fetchall():
        key = row["key"]
        lead_time_ms = _calc_lead_time_ms(row["created_at"], row["resolved_at"])
        cycle_time_ms = _calc_cycle_time_ms(status_cache.get(key, []), row["status"])
        cursor.execute(
            "INSERT OR REPLACE INTO h_metrics (issue_key, parent_key, project_key, status, lead_time_ms, cycle_time_ms) VALUES (?, ?, ?, ?, ?, ?)",
            (key, row["parent_key"], row["project_key"], row["status"], lead_time_ms, cycle_time_ms),
        )
        count += 1

    # Subtasks
    cursor.execute(
        f"SELECT key, parent_key, project_key, status, created_at, resolved_at FROM h_subtasks WHERE key IN ({placeholders})",
        issue_keys,
    )
    for row in cursor.fetchall():
        key = row["key"]
        lead_time_ms = _calc_lead_time_ms(row["created_at"], row["resolved_at"])
        cycle_time_ms = _calc_cycle_time_ms(status_cache.get(key, []), row["status"])
        cursor.execute(
            "INSERT OR REPLACE INTO h_metrics (issue_key, parent_key, project_key, status, lead_time_ms, cycle_time_ms) VALUES (?, ?, ?, ?, ?, ?)",
            (key, row["parent_key"], row["project_key"], row["status"], lead_time_ms, cycle_time_ms),
        )
        count += 1

    conn.commit()
    return count


# =============================================================================
# Epic Health: Throughput per-epic, Forecast Monte Carlo, Risk Assessment
# =============================================================================

from collections import defaultdict
from datetime import timedelta

from .forecast_core import simulate_completion_weeks, percentile_from_sorted


def get_epic_weekly_throughput(conn: sqlite3.Connection, epic_key: str, weeks: int = 12) -> list[dict]:
    """Retorna throughput semanal (stories Done/semana) específico de um épico.
    
    Retorna lista de dicts: [{"week": "2026-W30", "count": 3}, ...]
    Últimas N semanas, incluindo semanas com 0.
    """
    cursor = conn.cursor()
    cursor.execute('''
        SELECT resolved_at FROM h_stories
        WHERE parent_key = ? AND status IN ('Done', 'Canceled')
          AND resolved_at IS NOT NULL AND resolved_at != ''
    ''', (epic_key,))

    by_week: dict[str, int] = defaultdict(int)
    for row in cursor.fetchall():
        resolved_at = row["resolved_at"]
        try:
            dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
            iso = dt.isocalendar()
            wk = f"{iso[0]}-W{iso[1]:02d}"
            by_week[wk] += 1
        except (ValueError, TypeError):
            continue

    # Gera lista de últimas N semanas (incluindo as com 0)
    now = datetime.now()
    result = []
    for i in range(weeks - 1, -1, -1):
        dt = now - timedelta(weeks=i)
        iso = dt.isocalendar()
        wk = f"{iso[0]}-W{iso[1]:02d}"
        result.append({"week": wk, "count": by_week.get(wk, 0)})

    return result


def get_epic_monthly_throughput(conn: sqlite3.Connection, epic_key: str, months: int = 12) -> list[dict]:
    """Retorna throughput mensal (stories Done/mês) específico de um épico.
    
    Retorna lista de dicts: [{"month": "2026-03", "done": 1, "canceled": 0, "count": 1}, ...]
    Últimos N meses, incluindo meses com 0.
    """
    cursor = conn.cursor()
    cursor.execute('''
        SELECT status, resolved_at, updated_at FROM h_stories
        WHERE parent_key = ? AND status IN ('Done', 'Canceled')
    ''', (epic_key,))

    done_by_month: dict[str, int] = defaultdict(int)
    canceled_by_month: dict[str, int] = defaultdict(int)

    for row in cursor.fetchall():
        status = row["status"]
        date_str = row["resolved_at"] or row["updated_at"]
        if not date_str:
            continue
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            key = f"{dt.year}-{dt.month:02d}"
            if status == "Done":
                done_by_month[key] += 1
            else:
                canceled_by_month[key] += 1
        except (ValueError, TypeError):
            continue

    # Gera lista de últimos N meses (incluindo os com 0)
    now = datetime.now()
    result = []
    for i in range(months - 1, -1, -1):
        month = now.month - i
        year = now.year
        while month <= 0:
            month += 12
            year -= 1
        key = f"{year}-{month:02d}"
        done = done_by_month.get(key, 0)
        canceled = canceled_by_month.get(key, 0)
        result.append({"month": key, "done": done, "canceled": canceled, "count": done + canceled})

    return result


def _get_throughput_values(weekly_data: list[dict]) -> list[int]:
    """Extrai apenas os valores de count para uso no Monte Carlo."""
    return [w["count"] for w in weekly_data]


def monte_carlo_forecast(weekly_throughput: list[int], remaining: int, simulations: int = 1000) -> dict:
    """Monte Carlo simplificado: retorna previsão em semanas (P50, P70, P85, P95).
    
    Usa amostragem aleatória do throughput histórico para simular cenários futuros.
    """
    if not weekly_throughput or max(weekly_throughput) == 0 or remaining <= 0:
        return {"p50": 0, "p70": 0, "p85": 0, "p95": 0}

    # Remove semanas com 0 se houver throughput positivo (evita deadlock no sampling)
    positive_weeks = [t for t in weekly_throughput if t > 0]
    if not positive_weeks:
        return {"p50": 0, "p70": 0, "p85": 0, "p95": 0}

    # Núcleo compartilhado (mesma sequência de amostragem)
    results = simulate_completion_weeks(positive_weeks, remaining, simulations)

    def _pct(pct):
        return percentile_from_sorted(results, pct)

    return {"p50": _pct(50), "p70": _pct(70), "p85": _pct(85), "p95": _pct(95)}


def assess_epic_risk(
    due_date: str | None,
    forecast_p85: int,
    remaining: int,
    total: int,
    weekly_throughput: list[int],
) -> str:
    """Avalia risco do épico baseado em múltiplos fatores.
    
    Retorna: "low", "medium", "high", ou "critical".
    """
    if remaining == 0:
        return "done"

    risk_score = 0

    # Fator 1: Due date vs forecast P85
    if due_date and forecast_p85 > 0:
        try:
            due_dt = datetime.fromisoformat(due_date.replace("Z", "+00:00")).replace(tzinfo=None)
            weeks_until_due = (due_dt - datetime.now()).days / 7
            if weeks_until_due <= 0:
                risk_score += 4  # Já passou da due date
            elif weeks_until_due < forecast_p85:
                risk_score += 3  # Não vai dar tempo
            elif weeks_until_due < forecast_p85 * 1.2:
                risk_score += 1  # Apertado
        except (ValueError, TypeError):
            pass

    # Fator 2: Progresso muito baixo com muitos itens restantes
    progress = (total - remaining) / total if total > 0 else 0
    if remaining > 10 and progress < 0.2:
        risk_score += 2
    elif remaining > 5 and progress < 0.3:
        risk_score += 1

    # Fator 3: Forecast muito longo (>8 semanas)
    if forecast_p85 >= 12:
        risk_score += 2
    elif forecast_p85 >= 8:
        risk_score += 1

    # Fator 4: Throughput declinante (últimas 4 semanas < média geral)
    if len(weekly_throughput) >= 8:
        recent = weekly_throughput[-4:]
        earlier = weekly_throughput[:-4]
        avg_recent = sum(recent) / len(recent)
        avg_earlier = sum(earlier) / len(earlier) if earlier else 0
        if avg_earlier > 0 and avg_recent < avg_earlier * 0.5:
            risk_score += 2  # Throughput caiu >50%
        elif avg_earlier > 0 and avg_recent < avg_earlier * 0.75:
            risk_score += 1  # Throughput caiu >25%

    if risk_score >= 5:
        return "critical"
    elif risk_score >= 3:
        return "high"
    elif risk_score >= 1:
        return "medium"
    return "low"


def get_epic_health_data(conn: sqlite3.Connection, epic_key: str) -> dict:
    """Retorna dados completos de saúde de um épico.
    
    Inclui: progresso, throughput semanal, forecast Monte Carlo, risco, métricas de tempo.
    """
    cursor = conn.cursor()

    # Metadados do épico
    cursor.execute("SELECT * FROM h_epics WHERE key = ?", (epic_key,))
    epic_row = cursor.fetchone()
    if not epic_row:
        return None

    epic = dict(epic_row)

    # Stories filhas
    cursor.execute("SELECT key, status, resolved_at FROM h_stories WHERE parent_key = ?", (epic_key,))
    stories = cursor.fetchall()

    total = len(stories)
    done = sum(1 for s in stories if s["status"] in DONE_STATES)
    in_progress = sum(1 for s in stories if s["status"] in ACTIVE_STATES)
    remaining = total - done
    progress_pct = round(done / total * 100, 1) if total > 0 else 0

    # Throughput semanal (per-epic)
    weekly_data = get_epic_weekly_throughput(conn, epic_key, weeks=12)
    throughput_values = _get_throughput_values(weekly_data)

    # Throughput mensal (per-epic)
    monthly_data = get_epic_monthly_throughput(conn, epic_key, months=12)

    # Forecast Monte Carlo
    forecast = monte_carlo_forecast(throughput_values, remaining)

    # Risk assessment
    risk = assess_epic_risk(
        due_date=epic.get("due_date"),
        forecast_p85=forecast["p85"],
        remaining=remaining,
        total=total,
        weekly_throughput=throughput_values,
    )

    # Métricas de tempo (lead/cycle) das stories Done
    cursor.execute('''
        SELECT lead_time_ms, cycle_time_ms FROM h_metrics
        WHERE parent_key = ? AND status IN ('Done', 'Canceled') AND lead_time_ms > 0
    ''', (epic_key,))
    done_metrics = cursor.fetchall()

    lead_times = [r["lead_time_ms"] for r in done_metrics if r["lead_time_ms"] > 0]
    cycle_times = [r["cycle_time_ms"] for r in done_metrics if r["cycle_time_ms"] > 0]

    avg_lead_time_ms = int(sum(lead_times) / len(lead_times)) if lead_times else 0
    avg_cycle_time_ms = int(sum(cycle_times) / len(cycle_times)) if cycle_times else 0
    p85_lead_time_ms = _percentile_list(lead_times, 85)
    p85_cycle_time_ms = _percentile_list(cycle_times, 85)

    return {
        "epic": {
            "key": epic["key"],
            "summary": epic["summary"],
            "status": epic["status"],
            "assignee_name": epic.get("assignee_name", ""),
            "due_date": epic.get("due_date"),
            "project_key": epic.get("project_key", ""),
        },
        "progress": {
            "total": total,
            "done": done,
            "in_progress": in_progress,
            "remaining": remaining,
            "progress_pct": progress_pct,
        },
        "throughput": {
            "weekly": weekly_data,
            "monthly": monthly_data,
            "avg_per_week": round(sum(throughput_values) / len(throughput_values), 2) if throughput_values else 0,
            "avg_per_month": round(sum(m["count"] for m in monthly_data) / len(monthly_data), 2) if monthly_data else 0,
        },
        "forecast": forecast,
        "risk": risk,
        "metrics": {
            "avg_lead_time_ms": avg_lead_time_ms,
            "avg_cycle_time_ms": avg_cycle_time_ms,
            "p85_lead_time_ms": p85_lead_time_ms,
            "p85_cycle_time_ms": p85_cycle_time_ms,
        },
    }


def get_all_epics_health(conn: sqlite3.Connection) -> dict:
    """Retorna saúde de todos os épicos no hierarchy.db.
    
    Visão de portfólio: lista de épicos com resumo de health.
    """
    cursor = conn.cursor()
    clause, params = _excluded_where_clause("project_key")
    if clause:
        cursor.execute(f"SELECT key FROM h_epics WHERE {clause}", params)
    else:
        cursor.execute("SELECT key FROM h_epics")
    epic_keys = [row["key"] for row in cursor.fetchall()]

    epics = []
    summary = {"total": 0, "at_risk": 0, "on_track": 0, "done": 0}

    for key in epic_keys:
        health = get_epic_health_data(conn, key)
        if not health:
            continue
        epics.append(health)
        summary["total"] += 1
        if health["risk"] == "done":
            summary["done"] += 1
        elif health["risk"] in ("high", "critical"):
            summary["at_risk"] += 1
        else:
            summary["on_track"] += 1

    # Ordena: critical/high primeiro, depois por remaining desc
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "done": 4}
    epics.sort(key=lambda e: (risk_order.get(e["risk"], 9), -e["progress"]["remaining"]))

    return {"epics": epics, "summary": summary}


def _percentile_list(data: list[int], pct: int) -> int:
    """Calcula percentil de uma lista numérica."""
    if not data:
        return 0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * pct / 100)
    idx = min(idx, len(sorted_data) - 1)
    return sorted_data[idx]


# =============================================================================
# Initiative Health: Agregação de Épicos por Iniciativa (visão corporativa)
# =============================================================================


def _assess_initiative_risk(epic_risks: list[str]) -> str:
    """Avalia risco corporativo da iniciativa baseado nos riscos dos épicos filhos.
    
    Lógica: qualquer critical → critical; maioria high → high; etc.
    """
    if not epic_risks:
        return "low"

    # Remove "done" da análise de risco
    active_risks = [r for r in epic_risks if r != "done"]
    if not active_risks:
        return "done"

    if "critical" in active_risks:
        return "critical"

    high_count = active_risks.count("high")
    if high_count >= len(active_risks) * 0.5:
        return "critical"
    if high_count >= 1:
        return "high"

    medium_count = active_risks.count("medium")
    if medium_count >= len(active_risks) * 0.5:
        return "high"
    if medium_count >= 1:
        return "medium"

    return "low"


def get_initiative_weekly_throughput(conn: sqlite3.Connection, initiative_key: str, weeks: int = 12) -> list[dict]:
    """Retorna throughput semanal agregado (stories Done/semana) de todos os épicos da iniciativa.
    
    Retorna lista de dicts: [{"week": "2026-W30", "count": 3}, ...]
    """
    import json as _json
    cursor = conn.cursor()

    # Encontra épicos filhos da iniciativa
    cursor.execute("SELECT children_keys FROM h_initiatives WHERE key = ?", (initiative_key,))
    row = cursor.fetchone()
    if not row:
        return []

    children_keys = _json.loads(row["children_keys"] or "[]")
    if not children_keys:
        cursor.execute("SELECT key FROM h_epics WHERE parent_key = ?", (initiative_key,))
        children_keys = [r["key"] for r in cursor.fetchall()]

    if not children_keys:
        return []

    # Busca todas as stories Done de todos os épicos filhos
    placeholders = ",".join(["?" for _ in children_keys])
    cursor.execute(f'''
        SELECT resolved_at FROM h_stories
        WHERE parent_key IN ({placeholders}) AND status IN ('Done', 'Canceled')
          AND resolved_at IS NOT NULL AND resolved_at != ''
    ''', children_keys)

    by_week: dict[str, int] = defaultdict(int)
    for row in cursor.fetchall():
        resolved_at = row["resolved_at"]
        try:
            dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
            iso = dt.isocalendar()
            wk = f"{iso[0]}-W{iso[1]:02d}"
            by_week[wk] += 1
        except (ValueError, TypeError):
            continue

    # Gera lista de últimas N semanas (incluindo as com 0)
    now = datetime.now()
    result = []
    for i in range(weeks - 1, -1, -1):
        dt = now - timedelta(weeks=i)
        iso = dt.isocalendar()
        wk = f"{iso[0]}-W{iso[1]:02d}"
        result.append({"week": wk, "count": by_week.get(wk, 0)})

    return result


def get_initiative_monthly_throughput(conn: sqlite3.Connection, initiative_key: str, months: int = 6) -> list[dict]:
    """Retorna throughput mensal agregado de todos os épicos da iniciativa.
    
    Retorna lista de dicts: [{"month": "2026-03", "done": 3, "canceled": 2, "count": 5}, ...]
    Separado por Done e Canceled para visualização com cores distintas.
    """
    import json as _json
    cursor = conn.cursor()

    # Encontra épicos filhos da iniciativa
    cursor.execute("SELECT children_keys FROM h_initiatives WHERE key = ?", (initiative_key,))
    row = cursor.fetchone()
    if not row:
        return []

    children_keys = _json.loads(row["children_keys"] or "[]")
    if not children_keys:
        cursor.execute("SELECT key FROM h_epics WHERE parent_key = ?", (initiative_key,))
        children_keys = [r["key"] for r in cursor.fetchall()]

    if not children_keys:
        return []

    # Busca stories Done e Canceled com data (resolved_at ou updated_at como fallback)
    placeholders = ",".join(["?" for _ in children_keys])
    cursor.execute(f'''
        SELECT status, resolved_at, updated_at FROM h_stories
        WHERE parent_key IN ({placeholders}) AND status IN ('Done', 'Canceled')
    ''', children_keys)

    done_by_month: dict[str, int] = defaultdict(int)
    canceled_by_month: dict[str, int] = defaultdict(int)

    for row in cursor.fetchall():
        status = row["status"]
        date_str = row["resolved_at"] or row["updated_at"]
        if not date_str:
            continue
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            key = f"{dt.year}-{dt.month:02d}"
            if status == "Done":
                done_by_month[key] += 1
            else:
                canceled_by_month[key] += 1
        except (ValueError, TypeError):
            continue

    # Calendário fixo: todos os meses de 2026
    result = []
    for month in range(1, 13):
        key = f"2026-{month:02d}"
        done = done_by_month.get(key, 0)
        canceled = canceled_by_month.get(key, 0)
        result.append({"month": key, "done": done, "canceled": canceled, "count": done + canceled})

    return result


def get_initiative_pending_stories_by_duedate(conn: sqlite3.Connection, initiative_key: str) -> list[dict]:
    """Retorna stories pendentes (não Done/Canceled) agrupadas por mês usando due_date.

    Calendário fixo: Jan-Dez 2026.
    Retorna lista de dicts: [{"month": "2026-01", "pending": 0}, ..., {"month": "2026-12", "pending": N}]
    """
    import json as _json
    cursor = conn.cursor()

    # Encontra épicos filhos da iniciativa
    cursor.execute("SELECT children_keys FROM h_initiatives WHERE key = ?", (initiative_key,))
    row = cursor.fetchone()
    if not row:
        return []

    children_keys = _json.loads(row["children_keys"] or "[]")
    if not children_keys:
        cursor.execute("SELECT key FROM h_epics WHERE parent_key = ?", (initiative_key,))
        children_keys = [r["key"] for r in cursor.fetchall()]

    if not children_keys:
        return []

    # Busca stories pendentes (status != Done e != Canceled) com due_date preenchido
    placeholders = ",".join(["?" for _ in children_keys])
    cursor.execute(f'''
        SELECT due_date FROM h_stories
        WHERE parent_key IN ({placeholders})
          AND status NOT IN ('Done', 'Canceled')
          AND due_date IS NOT NULL AND due_date != ''
    ''', children_keys)

    pending_by_month: dict[str, int] = defaultdict(int)
    for row in cursor.fetchall():
        date_str = row["due_date"]
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            key = f"{dt.year}-{dt.month:02d}"
            pending_by_month[key] += 1
        except (ValueError, TypeError):
            continue

    # Calendário fixo: todos os meses de 2026
    result = []
    for month in range(1, 13):
        key = f"2026-{month:02d}"
        result.append({"month": key, "pending": pending_by_month.get(key, 0)})

    return result


def get_initiative_health_data(conn: sqlite3.Connection, initiative_key: str) -> dict | None:
    """Retorna dados completos de saúde de uma iniciativa.
    
    Agrega métricas de todos os épicos filhos:
    - Progresso geral (épicos Done/Total)
    - Progresso ponderado (stories Done de todos os épicos / total stories)
    - Risco corporativo (composição dos riscos dos épicos)
    - Times envolvidos (projetos distintos)
    - Throughput agregado + forecast
    - Métricas de tempo agregadas
    """
    import json as _json
    cursor = conn.cursor()

    # Metadados da iniciativa
    cursor.execute("SELECT * FROM h_initiatives WHERE key = ?", (initiative_key,))
    ini_row = cursor.fetchone()
    if not ini_row:
        return None

    ini = dict(ini_row)
    children_keys = _json.loads(ini.get("children_keys") or "[]")

    # Se children_keys vazio, fallback por parent_key
    if not children_keys:
        cursor.execute("SELECT key FROM h_epics WHERE parent_key = ?", (initiative_key,))
        children_keys = [r["key"] for r in cursor.fetchall()]

    # Obtém health de cada épico filho
    epics_health = []
    for ek in children_keys:
        eh = get_epic_health_data(conn, ek)
        if eh:
            epics_health.append(eh)

    # Progresso geral (épicos)
    total_epics = len(epics_health)
    epics_done = sum(1 for e in epics_health if e["risk"] == "done")

    # Progresso ponderado (stories)
    total_stories = sum(e["progress"]["total"] for e in epics_health)
    done_stories = sum(e["progress"]["done"] for e in epics_health)
    in_progress_stories = sum(e["progress"]["in_progress"] for e in epics_health)
    remaining_stories = total_stories - done_stories
    weighted_progress_pct = round(done_stories / total_stories * 100, 1) if total_stories > 0 else 0

    # Risco corporativo
    epic_risks = [e["risk"] for e in epics_health]
    corporate_risk = _assess_initiative_risk(epic_risks)

    # Times envolvidos (projetos distintos)
    teams = set()
    for eh in epics_health:
        pk = eh["epic"].get("project_key")
        if pk:
            teams.add(pk)
    # Também verifica projetos das stories (cross-project)
    if children_keys:
        placeholders = ",".join(["?" for _ in children_keys])
        cursor.execute(f"SELECT DISTINCT project_key FROM h_stories WHERE parent_key IN ({placeholders})", children_keys)
        for row in cursor.fetchall():
            if row["project_key"]:
                teams.add(row["project_key"])

    # Throughput agregado (todas stories de todos épicos)
    weekly_data = get_initiative_weekly_throughput(conn, initiative_key, weeks=12)
    throughput_values = _get_throughput_values(weekly_data)

    # Throughput mensal
    monthly_data = get_initiative_monthly_throughput(conn, initiative_key, months=12)

    # Pending stories por due_date (não Done/Canceled) — calendário fixo 2026
    pending_data = get_initiative_pending_stories_by_duedate(conn, initiative_key)

    # Forecast Monte Carlo (para stories restantes da iniciativa inteira)
    forecast = monte_carlo_forecast(throughput_values, remaining_stories)

    # Contagens adicionais: pendentes e sem due_date
    placeholders = ",".join(["?" for _ in children_keys])
    cursor.execute(f'''
        SELECT COUNT(*) as cnt FROM h_stories
        WHERE parent_key IN ({placeholders}) AND status NOT IN ('Done', 'Canceled')
    ''', children_keys)
    pending_count = cursor.fetchone()["cnt"]

    cursor.execute(f'''
        SELECT COUNT(*) as cnt FROM h_stories
        WHERE parent_key IN ({placeholders}) AND status NOT IN ('Done', 'Canceled')
          AND (due_date IS NULL OR due_date = '')
    ''', children_keys)
    no_duedate_count = cursor.fetchone()["cnt"]

    # Progresso planejado próximas 5 semanas:
    # Stories pendentes com due_date nos próximos 35 dias.
    # Não considera status: Open, To do, Refinamento (não estão realmente em andamento).
    now = datetime.now()
    five_weeks_later = now + timedelta(weeks=5)
    now_str = now.strftime("%Y-%m-%d")
    five_weeks_str = five_weeks_later.strftime("%Y-%m-%d")
    cursor.execute(f'''
        SELECT COUNT(*) as cnt FROM h_stories
        WHERE parent_key IN ({placeholders}) AND status NOT IN ('Done', 'Canceled')
          AND LOWER(TRIM(status)) NOT IN ('open', 'to do', 'refinamento', 'refinement')
          AND due_date IS NOT NULL AND due_date != ''
          AND due_date >= ? AND due_date <= ?
    ''', children_keys + [now_str, five_weeks_str])
    planned_next_5w = cursor.fetchone()["cnt"]
    # % projetada = (done + planejadas próximas 5 semanas) / total
    planned_progress_pct = round((done_stories + planned_next_5w) / total_stories * 100, 1) if total_stories > 0 else 0
    planned_range = {"start": now_str, "end": five_weeks_str}

    # Métricas de tempo agregadas (lead/cycle de todas stories Done da iniciativa)
    all_lead_times = []
    all_cycle_times = []
    for eh in epics_health:
        mt = eh["metrics"]
        if mt["avg_lead_time_ms"] > 0:
            all_lead_times.append(mt["avg_lead_time_ms"])
        if mt["avg_cycle_time_ms"] > 0:
            all_cycle_times.append(mt["avg_cycle_time_ms"])

    avg_lead_time_ms = int(sum(all_lead_times) / len(all_lead_times)) if all_lead_times else 0
    avg_cycle_time_ms = int(sum(all_cycle_times) / len(all_cycle_times)) if all_cycle_times else 0

    return {
        "initiative": {
            "key": ini["key"],
            "summary": ini["summary"],
            "status": ini["status"],
            "assignee_name": ini.get("assignee_name", ""),
            "due_date": ini.get("due_date"),
            "project_key": ini.get("project_key", ""),
        },
        "progress": {
            "total_epics": total_epics,
            "epics_done": epics_done,
            "total_stories": total_stories,
            "done_stories": done_stories,
            "in_progress_stories": in_progress_stories,
            "remaining_stories": remaining_stories,
            "pending_count": pending_count,
            "no_duedate_count": no_duedate_count,
            "planned_next_5w": planned_next_5w,
            "planned_progress_pct": planned_progress_pct,
            "planned_range": planned_range,
            "epics_progress_pct": round(epics_done / total_epics * 100, 1) if total_epics > 0 else 0,
            "weighted_progress_pct": weighted_progress_pct,
        },
        "throughput": {
            "weekly": weekly_data,
            "monthly": monthly_data,
            "pending_monthly": pending_data,
            "avg_per_week": round(sum(throughput_values) / len(throughput_values), 2) if throughput_values else 0,
            "avg_per_month": round(sum(m["count"] for m in monthly_data) / len(monthly_data), 2) if monthly_data else 0,
        },
        "forecast": forecast,
        "risk": corporate_risk,
        "teams": sorted(list(teams)),
        "epics": epics_health,
        "metrics": {
            "avg_lead_time_ms": avg_lead_time_ms,
            "avg_cycle_time_ms": avg_cycle_time_ms,
        },
    }


def get_all_initiatives_health(conn: sqlite3.Connection) -> dict:
    """Retorna saúde de todas as iniciativas no hierarchy.db.
    
    Visão corporativa: lista de iniciativas com resumo de health.
    """
    cursor = conn.cursor()
    clause, params = _excluded_where_clause("project_key")
    if clause:
        cursor.execute(f"SELECT key FROM h_initiatives WHERE {clause}", params)
    else:
        cursor.execute("SELECT key FROM h_initiatives")
    ini_keys = [row["key"] for row in cursor.fetchall()]

    initiatives = []
    summary = {"total": 0, "at_risk": 0, "on_track": 0, "done": 0}

    for key in ini_keys:
        health = get_initiative_health_data(conn, key)
        if not health:
            continue
        initiatives.append(health)
        summary["total"] += 1
        if health["risk"] == "done":
            summary["done"] += 1
        elif health["risk"] in ("high", "critical"):
            summary["at_risk"] += 1
        else:
            summary["on_track"] += 1

    # Ordena: critical/high primeiro
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "done": 4}
    initiatives.sort(key=lambda i: risk_order.get(i["risk"], 9))

    return {"initiatives": initiatives, "summary": summary}


# =============================================================================
# Dashboard V2: Visão consolidada (Initiatives + Épicos Órfãos)
# =============================================================================


def get_dashboard_v2_data(conn: sqlite3.Connection) -> dict:
    """Retorna dados consolidados para o Dashboard V2.
    
    Estrutura:
    - big_numbers: contagens globais (épicos total, iniciativas com épicos, épicos órfãos)
    - initiatives: lista de initiative health (mesmos dados do initiative-health)
    - orphan_epics: epic health apenas dos épicos SEM iniciativa vinculada
    """
    import json as _json
    cursor = conn.cursor()

    excluded = get_excluded_projects()
    epic_clause, epic_params = _excluded_where_clause("project_key", excluded)
    ini_clause, ini_params = _excluded_where_clause("project_key", excluded)

    # --- Big Numbers ---
    if epic_clause:
        cursor.execute(f"SELECT COUNT(*) as c FROM h_epics WHERE {epic_clause}", epic_params)
    else:
        cursor.execute("SELECT COUNT(*) as c FROM h_epics")
    total_epics = cursor.fetchone()["c"]

    # Iniciativas que têm épicos (children_keys não vazio OU existem épicos com parent_key apontando)
    if ini_clause:
        cursor.execute(f"SELECT key, children_keys FROM h_initiatives WHERE {ini_clause}", ini_params)
    else:
        cursor.execute("SELECT key, children_keys FROM h_initiatives")
    all_initiatives = cursor.fetchall()

    # Conjunto de épicos válidos (não excluídos), usado para filtrar children e órfãos
    if epic_clause:
        cursor.execute(f"SELECT key FROM h_epics WHERE {epic_clause}", epic_params)
    else:
        cursor.execute("SELECT key FROM h_epics")
    valid_epic_keys = [r["key"] for r in cursor.fetchall()]
    valid_epic_set = set(valid_epic_keys)

    initiatives_with_epics = 0
    linked_epic_keys = set()

    for ini in all_initiatives:
        children = _json.loads(ini["children_keys"] or "[]")
        if not children:
            # Fallback: verifica por parent_key
            cursor.execute("SELECT key FROM h_epics WHERE parent_key = ?", (ini["key"],))
            children = [r["key"] for r in cursor.fetchall()]
        # Considera apenas épicos não excluídos
        children = [c for c in children if c in valid_epic_set]
        if children:
            initiatives_with_epics += 1
            linked_epic_keys.update(children)

    # Épicos órfãos: não estão vinculados a nenhuma iniciativa (apenas épicos válidos)
    all_epic_keys = valid_epic_keys
    orphan_epic_keys = [k for k in all_epic_keys if k not in linked_epic_keys]
    total_orphans = len(orphan_epic_keys)

    big_numbers = {
        "total_epics": total_epics,
        "total_initiatives": len(all_initiatives),
        "initiatives_with_epics": initiatives_with_epics,
        "orphan_epics": total_orphans,
    }

    # --- Initiatives Health (reutiliza função existente) ---
    initiatives_data = get_all_initiatives_health(conn)

    # --- Orphan Epics Health ---
    orphan_epics = []
    orphan_summary = {"total": 0, "at_risk": 0, "on_track": 0, "done": 0}

    for key in orphan_epic_keys:
        health = get_epic_health_data(conn, key)
        if not health:
            continue
        orphan_epics.append(health)
        orphan_summary["total"] += 1
        if health["risk"] == "done":
            orphan_summary["done"] += 1
        elif health["risk"] in ("high", "critical"):
            orphan_summary["at_risk"] += 1
        else:
            orphan_summary["on_track"] += 1

    # Ordena: critical/high primeiro
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "done": 4}
    orphan_epics.sort(key=lambda e: (risk_order.get(e["risk"], 9), -e["progress"]["remaining"]))

    return {
        "big_numbers": big_numbers,
        "initiatives": initiatives_data,
        "orphan_epics": {"epics": orphan_epics, "summary": orphan_summary},
    }
