"""Regras de diagnóstico de previsibilidade (Wave 2).

Analisa throughput, estabilidade, tendência e backlog aging.
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

from .engine import InsightsEngine, Insight


def register_throughput_rules(engine: InsightsEngine) -> None:
    """Registra todas as regras de previsibilidade na engine."""
    engine.register("throughput_stability", rule_throughput_stability)
    engine.register("throughput_declining", rule_throughput_declining)
    engine.register("throughput_increasing", rule_throughput_increasing)
    engine.register("aging_backlog_risk", rule_aging_backlog_risk)


# --- Helpers ---

def _get_weekly_throughput(conn: sqlite3.Connection, project_key: str, weeks: int = 12) -> list[int]:
    """Retorna lista de throughput semanal (últimas N semanas)."""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT resolved_at
        FROM issues
        WHERE status = 'Done' AND resolved_at IS NOT NULL AND resolved_at != ''
          AND project_key = ?
    ''', (project_key,))
    rows = cursor.fetchall()

    if not rows:
        return []

    by_week: dict[str, int] = defaultdict(int)
    for (resolved_at,) in rows:
        try:
            dt = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
            iso = dt.isocalendar()
            week_key = f"{iso[0]}-W{iso[1]:02d}"
            by_week[week_key] += 1
        except (ValueError, TypeError):
            continue

    sorted_weeks = sorted(by_week.keys())[-weeks:]
    return [by_week[w] for w in sorted_weeks]


# --- Rules ---

def rule_throughput_stability(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Avalia estabilidade do throughput (CV < 0.3 = previsível)."""
    weekly = _get_weekly_throughput(conn, project_key, weeks=8)
    if len(weekly) < 4:
        return []

    mean = sum(weekly) / len(weekly)
    if mean == 0:
        return []

    variance = sum((x - mean) ** 2 for x in weekly) / len(weekly)
    std_dev = math.sqrt(variance)
    cv = std_dev / mean

    if cv < 0.5:
        return [Insight(
            category="predictability",
            severity="healthy",
            title="Throughput estável — forecast confiável",
            description=f"Throughput médio de {mean:.1f} items/semana com variação de apenas {cv*100:.0f}% "
                        f"nas últimas {len(weekly)} semanas. Monte Carlo Forecast será preciso.",
            metric="throughput_cv",
            value=round(cv, 2),
        )]
    elif cv <= 0.7:
        return [Insight(
            category="predictability",
            severity="info",
            title="Throughput moderadamente variável",
            description=f"Throughput médio de {mean:.1f} items/semana com variação de {cv*100:.0f}% "
                        f"(entre {min(weekly)} e {max(weekly)}/semana). Forecast terá margem moderada.",
            metric="throughput_cv",
            value=round(cv, 2),
        )]
    else:
        return [Insight(
            category="predictability",
            severity="warning",
            title="Throughput muito instável — forecast impreciso",
            description=f"Throughput varia entre {min(weekly)} e {max(weekly)} items/semana "
                        f"(coeficiente de variação: {cv*100:.0f}%). Previsões terão margem de erro alta.",
            metric="throughput_cv",
            value=round(cv, 2),
            threshold=0.7,
            recommendation="Investigar causas da instabilidade: sprints irregulares, "
                           "dependências externas, ou mix de itens grandes e pequenos.",
        )]


def rule_throughput_declining(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Detecta throughput caindo por 3+ semanas consecutivas."""
    weekly = _get_weekly_throughput(conn, project_key, weeks=8)
    if len(weekly) < 4:
        return []

    # Verifica últimas 4 semanas
    recent = weekly[-4:]
    consecutive_decreases = 0
    for i in range(1, len(recent)):
        if recent[i] < recent[i - 1]:
            consecutive_decreases += 1
        else:
            consecutive_decreases = 0

    if consecutive_decreases >= 3:
        drop_pct = ((recent[0] - recent[-1]) / recent[0] * 100) if recent[0] > 0 else 0
        return [Insight(
            category="predictability",
            severity="warning",
            title="Throughput em queda — capacidade de entrega reduzindo",
            description=f"Throughput caiu por {consecutive_decreases} semanas consecutivas "
                        f"(de {recent[0]} para {recent[-1]} items/semana, -{drop_pct:.0f}%). "
                        f"A velocidade de entrega está diminuindo.",
            metric="throughput_trend",
            value=recent[-1],
            recommendation="Verificar: férias/ausências, aumento de WIP, bloqueios frequentes, "
                           "ou itens maiores entrando no fluxo.",
        )]
    return []


def rule_throughput_increasing(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Detecta throughput crescendo por 3+ semanas (sinal positivo)."""
    weekly = _get_weekly_throughput(conn, project_key, weeks=8)
    if len(weekly) < 4:
        return []

    recent = weekly[-4:]
    consecutive_increases = 0
    for i in range(1, len(recent)):
        if recent[i] > recent[i - 1]:
            consecutive_increases += 1
        else:
            consecutive_increases = 0

    if consecutive_increases >= 3:
        return [Insight(
            category="predictability",
            severity="healthy",
            title="Throughput em alta — capacidade crescendo",
            description=f"Throughput cresceu por {consecutive_increases} semanas consecutivas "
                        f"(de {recent[0]} para {recent[-1]} items/semana). "
                        f"Ritmo de entrega acelerando.",
            metric="throughput_trend",
            value=recent[-1],
        )]
    return []


def rule_aging_backlog_risk(conn: sqlite3.Connection, project_key: str) -> list[Insight]:
    """Detecta backlog com muitas issues antigas (risco de poluição de métricas)."""
    cursor = conn.cursor()
    now = datetime.now()

    cursor.execute('''
        SELECT COUNT(*) FROM issues
        WHERE project_key = ? AND status != 'Done'
          AND updated_at IS NOT NULL AND updated_at != ''
    ''', (project_key,))
    total_open = cursor.fetchone()[0]

    if total_open == 0:
        return []

    cursor.execute('''
        SELECT updated_at FROM issues
        WHERE project_key = ? AND status != 'Done'
          AND updated_at IS NOT NULL AND updated_at != ''
    ''', (project_key,))
    rows = cursor.fetchall()

    stale_90d = 0
    stale_180d = 0
    for (updated_at,) in rows:
        try:
            dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).replace(tzinfo=None)
            days = (now - dt).days
            if days >= 180:
                stale_180d += 1
            elif days >= 90:
                stale_90d += 1
        except (ValueError, TypeError):
            continue

    stale_total = stale_90d + stale_180d
    stale_pct = (stale_total / total_open * 100) if total_open > 0 else 0

    if stale_180d >= 10:
        return [Insight(
            category="predictability",
            severity="warning",
            title=f"Backlog com {stale_180d} issues abandonadas (>180 dias)",
            description=f"{stale_total} de {total_open} issues abertas ({stale_pct:.0f}%) estão inativas há mais de 90 dias. "
                        f"{stale_180d} delas há mais de 180 dias. "
                        f"Se forem fechadas como Done, distorcem Lead Time e percentis.",
            metric="aging_backlog_180d",
            value=stale_180d,
            threshold=10,
            recommendation="Cancelar issues inativas há >180 dias (não resolver como Done). "
                           "Isso mantém as métricas limpas e o backlog gerenciável.",
        )]
    elif stale_total >= 20 and stale_pct > 30:
        return [Insight(
            category="predictability",
            severity="info",
            title=f"Backlog com {stale_pct:.0f}% de issues inativas",
            description=f"{stale_total} de {total_open} issues abertas estão sem atividade há >90 dias. "
                        f"Considere uma revisão periódica do backlog.",
            metric="aging_backlog_pct",
            value=round(stale_pct, 1),
        )]
    return []
