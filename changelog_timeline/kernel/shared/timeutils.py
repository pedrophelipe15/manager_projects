"""Utilitários de tempo compartilhados — fonte única de verdade.

Centraliza `week_to_date_range`, que antes estava duplicado em
wave2_predictability/throughput.py, wave4_portfolio/cross_project.py,
insights/rules_flow.py e insights/rules_throughput.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def week_to_date_range(week_str: str) -> str:
    """Converte '2026-W32' para '04/08 - 10/08' (segunda a domingo, ISO week).

    ISO week: a segunda-feira da semana 1 contém 4 de janeiro. Em caso de
    formato inválido, retorna a string original.
    """
    try:
        year_str, w_str = week_str.split("-W")
        year = int(year_str)
        week = int(w_str)
        jan4 = datetime(year, 1, 4)
        day_of_week = jan4.isoweekday()  # 1=seg ... 7=dom
        monday = jan4 - timedelta(days=day_of_week - 1) + timedelta(weeks=week - 1)
        sunday = monday + timedelta(days=6)
        return f"{monday.strftime('%d/%m')} - {sunday.strftime('%d/%m')}"
    except (ValueError, TypeError):
        return week_str
