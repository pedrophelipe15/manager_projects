"""Regras de diagnóstico de fluxo (Wave 1).

Analisa tendências de Lead Time, Cycle Time, Flow Efficiency e gargalos.
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

from .engine import InsightsEngine, Insight
from ..timeutils import week_to_date_range


def register_flow_rules(engine: InsightsEngine) -> None:
    """Registra todas as regras de fluxo na engine."""
    engine.register("lead_time_spikes", rule_lead_time_spikes)
    engine.register("lead_time_trend", rule_lead_time_trend)
    engine.register("cycle_time_trend", rule_cycle_time_trend)
    engine.register("lead_cycle_gap", rule_lead_cycle_gap)
    engine.register("lead_time_volatility", rule_lead_time_volatility)
    engine.register("cycle_time_stability", rule_cycle_time_stability)
    engine.register("flow_efficiency_low", rule_flow_efficiency_low)
    engine.register("bottleneck_status", rule_bottleneck_status)


# --- Helpers ---

def _get_weekly_percentiles(conn: sqlite3.Connection, project_key: str, weeks: int = 12) -> list[dict]:
    """Retorna P85 semanal de lead time e cycle time para as últimas N semanas."""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT i.resolved_at, m.lead_time_ms, m.cycle_time_ms
        FROM issues i
        INNER JOIN metrics m ON i.key = m.issue_key
        WHERE i.status = 'Done' AND i.resolved_at IS NOT NULL AND i.resolved_at != ''
          AND m.lead_time_ms > 0 AND i.project_key = ?
        ORDER BY i.resolved_at
    ''', (project_key,))
    rows = cursor.fetchall()

    if not rows:
        return []

    by_week: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for resolved_at, lead_ms, cycle_ms in rows:
        try:
            dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
            iso = dt.isocalendar()
            week_key = f"{iso[0]}-W{iso[1]:02d}"
            by_week[week_key].append((lead_ms, cycle_ms))
        except (ValueError, TypeError):
            continue

    def p85(values: list[int]) -> int:
        if not values:
            return 0
        s = sorted(values)
        idx = max(0, min(int(math.ceil(0.85 * len(s))) - 1, len(s) - 1))
        return s[idx]

    sorted_weeks = sorted(by_week.keys())[-weeks:]
    result = []
    for wk in sorted_weeks:
        items = by_week[wk]
        leads = [x[0] for x in items]
        cycles = [x[1] for x in items if x[1] > 0]
        result.append({
            "week": wk,
            "count": len(items),
            "lead_p85": p85(leads),
            "cycle_p85": p85(cycles) if cycles else 0,
        })
    return result


def _ms_to_days(ms: int) -> float:
    return ms / (1000 * 60 * 60 * 24)


def _fmt_days(ms: int) -> str:
    days = _ms_to_days(ms)
    if days < 1:
        return f"{ms / (1000*60*60):.0f}h"
    return f"{days:.1f}d"


# --- Rules ---

def rule_lead_time_spikes(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """1.1 — Detecta picos de Lead Time P85 (>3x mediana histórica)."""
    weekly = _get_weekly_percentiles(conn, project_key, weeks=26)
    if len(weekly) < 4:
        return []

    lead_values = [w["lead_p85"] for w in weekly if w["lead_p85"] > 0]
    if not lead_values:
        return []

    median_lead = sorted(lead_values)[len(lead_values) // 2]
    threshold = median_lead * 3

    spikes = [w for w in weekly[-8:] if w["lead_p85"] > threshold]

    if spikes:
        spike_weeks = ", ".join(week_to_date_range(w["week"]) for w in spikes)
        max_spike = max(w["lead_p85"] for w in spikes)
        return [Insight(
            category="flow",
            severity="warning",
            title="Picos de Lead Time detectados",
            description=f"Lead Time P85 atingiu {_fmt_days(max_spike)} em semanas recentes ({spike_weeks}), "
                        f"mais de 3x a mediana histórica ({_fmt_days(median_lead)}). "
                        f"Provável causa: issues antigas de backlog sendo fechadas nessas semanas.",
            metric="lead_time_p85_weekly",
            value=_ms_to_days(max_spike),
            threshold=_ms_to_days(threshold),
            recommendation="Avaliar se issues com lead time >180d deveriam ser canceladas em vez de resolvidas, "
                           "ou separar métricas de 'fluxo normal' vs 'débito técnico'.",
        )]
    return []


def rule_lead_time_trend(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """1.2 — Detecta tendência crescente de Lead Time P85 por 3+ semanas."""
    weekly = _get_weekly_percentiles(conn, project_key, weeks=12)
    if len(weekly) < 4:
        return []

    # Verifica últimas 4 semanas
    recent = weekly[-4:]
    lead_values = [w["lead_p85"] for w in recent]

    consecutive_increases = 0
    for i in range(1, len(lead_values)):
        if lead_values[i] > lead_values[i - 1]:
            consecutive_increases += 1
        else:
            consecutive_increases = 0

    if consecutive_increases >= 3:
        pct_increase = ((lead_values[-1] - lead_values[-4]) / lead_values[-4] * 100) if lead_values[-4] > 0 else 0
        return [Insight(
            category="flow",
            severity="warning",
            title="Lead Time em tendência de alta",
            description=f"Lead Time P85 cresceu por {consecutive_increases} semanas consecutivas "
                        f"(de {_fmt_days(lead_values[-4])} para {_fmt_days(lead_values[-1])}, +{pct_increase:.0f}%). "
                        f"O tempo de entrega está piorando.",
            metric="lead_time_p85_trend",
            value=_ms_to_days(lead_values[-1]),
            recommendation="Investigar causas: WIP alto, bloqueios frequentes, ou issues entrando em filas longas.",
        )]
    return []


def rule_cycle_time_trend(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """1.3 — Detecta tendência crescente de Cycle Time P85 por 3+ semanas."""
    weekly = _get_weekly_percentiles(conn, project_key, weeks=12)
    if len(weekly) < 4:
        return []

    recent = weekly[-4:]
    cycle_values = [w["cycle_p85"] for w in recent if w["cycle_p85"] > 0]

    if len(cycle_values) < 4:
        return []

    consecutive_increases = 0
    for i in range(1, len(cycle_values)):
        if cycle_values[i] > cycle_values[i - 1]:
            consecutive_increases += 1
        else:
            consecutive_increases = 0

    if consecutive_increases >= 3:
        pct_increase = ((cycle_values[-1] - cycle_values[-4]) / cycle_values[-4] * 100) if cycle_values[-4] > 0 else 0
        return [Insight(
            category="flow",
            severity="warning",
            title="Cycle Time em tendência de alta",
            description=f"Cycle Time P85 cresceu por {consecutive_increases} semanas consecutivas "
                        f"(de {_fmt_days(cycle_values[-4])} para {_fmt_days(cycle_values[-1])}, +{pct_increase:.0f}%). "
                        f"A execução está desacelerando.",
            metric="cycle_time_p85_trend",
            value=_ms_to_days(cycle_values[-1]),
            recommendation="Verificar: WIP excessivo por pessoa, bloqueios recorrentes, ou complexidade crescente das issues.",
        )]
    return []


def rule_lead_cycle_gap(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """1.4 — Detecta gap grande entre Lead Time e Cycle Time (>5x = espera excessiva)."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p85_ms FROM metrics_percentiles
        WHERE project_key = ? AND metric_type = 'lead_time'
    """, (project_key,))
    row = cursor.fetchone()
    lead_p85 = row[0] if row else 0

    cursor.execute("""
        SELECT p85_ms FROM metrics_percentiles
        WHERE project_key = ? AND metric_type = 'cycle_time'
    """, (project_key,))
    row = cursor.fetchone()
    cycle_p85 = row[0] if row else 0

    if lead_p85 == 0 or cycle_p85 == 0:
        return []

    ratio = lead_p85 / cycle_p85

    if ratio > 5:
        return [Insight(
            category="flow",
            severity="warning",
            title="Issues esperam demais em filas",
            description=f"Lead Time P85 ({_fmt_days(lead_p85)}) é {ratio:.1f}x maior que o Cycle Time P85 ({_fmt_days(cycle_p85)}). "
                        f"Issues passam {((ratio - 1) / ratio * 100):.0f}% do tempo aguardando em filas, não sendo trabalhadas.",
            metric="lead_cycle_ratio",
            value=round(ratio, 1),
            threshold=5.0,
            recommendation="Reduzir WIP total, priorizar mais agressivamente, ou implementar limites de fila por status.",
        )]
    elif ratio > 3:
        return [Insight(
            category="flow",
            severity="info",
            title="Gap moderado entre Lead e Cycle Time",
            description=f"Lead Time P85 ({_fmt_days(lead_p85)}) é {ratio:.1f}x maior que o Cycle Time P85 ({_fmt_days(cycle_p85)}). "
                        f"Há espaço para melhorar o tempo em filas.",
            metric="lead_cycle_ratio",
            value=round(ratio, 1),
        )]
    return []


def rule_lead_time_volatility(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """1.5 — Detecta alta volatilidade no Lead Time P85 semanal."""
    weekly = _get_weekly_percentiles(conn, project_key, weeks=12)
    if len(weekly) < 6:
        return []

    lead_values = [w["lead_p85"] for w in weekly if w["lead_p85"] > 0]
    if len(lead_values) < 6:
        return []

    mean = sum(lead_values) / len(lead_values)
    variance = sum((x - mean) ** 2 for x in lead_values) / len(lead_values)
    std_dev = math.sqrt(variance)

    cv = (std_dev / mean) if mean > 0 else 0  # Coeficiente de variação

    if cv > 1.0:
        return [Insight(
            category="flow",
            severity="warning",
            title="Fluxo imprevisível — Lead Time muito volátil",
            description=f"O Lead Time P85 semanal varia entre {_fmt_days(min(lead_values))} e {_fmt_days(max(lead_values))} "
                        f"(coeficiente de variação: {cv:.1f}x). Impossível dar previsão confiável de entrega.",
            metric="lead_time_cv",
            value=round(cv, 2),
            threshold=1.0,
            recommendation="Causa provável: mix de issues antigas e novas sendo fechadas juntas. "
                           "Separar métricas por 'idade' ou tipo pode dar previsibilidade.",
        )]
    return []


def rule_cycle_time_stability(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """1.6 — Detecta estabilidade positiva no Cycle Time (CV < 0.3 por 4+ semanas)."""
    weekly = _get_weekly_percentiles(conn, project_key, weeks=8)
    if len(weekly) < 4:
        return []

    cycle_values = [w["cycle_p85"] for w in weekly[-4:] if w["cycle_p85"] > 0]
    if len(cycle_values) < 4:
        return []

    mean = sum(cycle_values) / len(cycle_values)
    variance = sum((x - mean) ** 2 for x in cycle_values) / len(cycle_values)
    std_dev = math.sqrt(variance)
    cv = (std_dev / mean) if mean > 0 else 0

    if cv < 0.3:
        return [Insight(
            category="flow",
            severity="healthy",
            title="Cycle Time estável — execução consistente",
            description=f"Cycle Time P85 se mantém estável em ~{_fmt_days(int(mean))} nas últimas 4 semanas "
                        f"(variação de apenas {cv*100:.0f}%). A velocidade de execução é previsível.",
            metric="cycle_time_cv",
            value=round(cv, 2),
        )]
    return []


def rule_flow_efficiency_low(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """1.7 — Detecta Flow Efficiency baixa (<15%)."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT AVG(flow_efficiency) FROM metrics_flow WHERE project_key = ?
    """, (project_key,))
    row = cursor.fetchone()
    avg_eff = row[0] if row and row[0] else 0

    if avg_eff == 0:
        return []

    if avg_eff < 15:
        return [Insight(
            category="flow",
            severity="warning",
            title="Flow Efficiency baixa — espera excessiva",
            description=f"A eficiência média do fluxo é {avg_eff:.1f}% — issues passam "
                        f"{100 - avg_eff:.0f}% do lead time paradas em filas ou aguardando ação.",
            metric="flow_efficiency_avg",
            value=round(avg_eff, 1),
            threshold=15.0,
            recommendation="Reduzir tamanho de lote, limitar WIP, ou eliminar handoffs desnecessários entre etapas.",
        )]
    elif avg_eff >= 40:
        return [Insight(
            category="flow",
            severity="healthy",
            title="Flow Efficiency excelente",
            description=f"Eficiência do fluxo em {avg_eff:.1f}% — acima da referência de 40%. "
                        f"Issues fluem com pouca espera.",
            metric="flow_efficiency_avg",
            value=round(avg_eff, 1),
        )]
    return []


def rule_bottleneck_status(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """1.8 — Identifica gargalo claro (status com P85 > 2x o segundo maior)."""
    cursor = conn.cursor()

    # Statuses excluídos (mesma lógica da API time-per-status)
    excluded = {"Open", "Backlog", "To do", "Canceled", "Reject", "Removed", "Done"}

    cursor.execute("""
        SELECT mps.status, mps.duration_ms
        FROM metrics_per_status mps
        INNER JOIN issues i ON mps.issue_key = i.key
        WHERE mps.project_key = ? AND i.status = 'Done'
    """, (project_key,))
    rows = cursor.fetchall()

    if not rows:
        return []

    # Agrupa durações por status
    by_status: dict[str, list[int]] = defaultdict(list)
    for status, duration_ms in rows:
        if status not in excluded:
            by_status[status].append(duration_ms)

    if len(by_status) < 2:
        return []

    # Calcula P85 por status
    def p85(values: list[int]) -> int:
        s = sorted(values)
        idx = max(0, min(int(math.ceil(0.85 * len(s))) - 1, len(s) - 1))
        return s[idx]

    status_p85 = [(status, p85(durations)) for status, durations in by_status.items()]
    status_p85.sort(key=lambda x: x[1], reverse=True)

    top_status, top_p85 = status_p85[0]
    second_p85 = status_p85[1][1] if len(status_p85) > 1 else 0

    if second_p85 > 0 and top_p85 > second_p85 * 2:
        ratio = top_p85 / second_p85
        return [Insight(
            category="flow",
            severity="info",
            title=f"Gargalo claro identificado: {top_status}",
            description=f"O status '{top_status}' tem P85 de {_fmt_days(top_p85)}, "
                        f"{ratio:.1f}x maior que o segundo maior ({status_p85[1][0]}: {_fmt_days(second_p85)}). "
                        f"Este é o principal ponto de acúmulo no fluxo.",
            metric="bottleneck_status",
            value=top_status,
            recommendation=f"Investigar por que issues ficam presas em '{top_status}'. "
                           f"Possíveis causas: dependência externa, falta de capacity, ou processo burocrático.",
        )]
    return []
