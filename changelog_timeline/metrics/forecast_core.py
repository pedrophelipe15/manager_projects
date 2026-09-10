"""Núcleo compartilhado de simulação Monte Carlo de conclusão.

Centraliza o laço de amostragem que estava duplicado em
wave2_predictability/forecast.py e wave4_portfolio/epic_health.py.

O laço replica EXATAMENTE o comportamento original (mesma sequência de
`random.choice`), de modo que resultados com `random.seed` fixo permanecem
idênticos após a refatoração.
"""

from __future__ import annotations

import math
import random

# Trava de segurança: nenhuma simulação passa de 52 semanas (1 ano).
MAX_WEEKS = 52


def simulate_completion_weeks(
    weekly_throughputs: list[int],
    remaining_items: int,
    simulations: int,
) -> list[int]:
    """Roda a simulação Monte Carlo e retorna a lista ORDENADA de semanas.

    Para cada simulação, sorteia semanas do histórico (`random.choice`) e
    acumula até atingir `remaining_items`, limitado a MAX_WEEKS. A lista
    retornada vem ordenada (asc) para cálculo de percentis pelo chamador.
    """
    results: list[int] = []
    for _ in range(simulations):
        total = 0
        weeks_needed = 0
        while total < remaining_items:
            total += random.choice(weekly_throughputs)
            weeks_needed += 1
            if weeks_needed >= MAX_WEEKS:
                break
        results.append(weeks_needed)
    results.sort()
    return results


def percentile_from_sorted(sorted_results: list[int], pct: float) -> int:
    """Percentil (método ceil) sobre uma lista já ordenada. 0 se vazia."""
    if not sorted_results:
        return 0
    idx = max(0, min(int(math.ceil(pct / 100.0 * len(sorted_results))) - 1, len(sorted_results) - 1))
    return sorted_results[idx]
