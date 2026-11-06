from metrics.wave2_predictability import get_aging_backlog
from metrics.wave2_predictability import get_throughput_weekly
from metrics.wave2_predictability import monte_carlo_forecast
from metrics.wave2_predictability.forecast import get_open_epics
from core.db import get_db_connection
from fastapi import APIRouter

router = APIRouter()


# --- Wave 2: Previsibilidade ---


@router.get("/api/metrics/wave2/throughput")
def api_throughput(project_key: str, weeks: int = 26):
    """Retorna throughput semanal (issues Done por semana) total e por tipo."""
    conn = get_db_connection()
    result = get_throughput_weekly(conn, project_key, weeks)
    conn.close()
    return result


@router.get("/api/metrics/wave2/throughput-impact")
def api_throughput_impact(project_key: str, cutoff_week: str, weeks: int = 26):
    """Calcula o impacto antes/depois de um MARCO no throughput semanal.

    Fonte unica da regra do modo "Analisar melhoria": dado o marco (cutoff_week,
    ex. '2026-W33' = 1a semana do periodo 'depois'), retorna medias por semana,
    ganho de ritmo e a JANELA COMPARAVEL (mesmo nº de semanas dos dois lados).
    """
    conn = get_db_connection()
    tp = get_throughput_weekly(conn, project_key, weeks)
    conn.close()

    weekly = tp.get("weekly", [])
    if not weekly:
        return {"error": "sem dados de throughput", "weekly": 0}

    week_keys = [w["week"] for w in weekly]
    totals = [w["total"] for w in weekly]

    # Indice de corte = posicao de cutoff_week (1a semana "depois"). Se nao achar,
    # usa o meio da serie como fallback seguro.
    try:
        cut = week_keys.index(cutoff_week)
    except ValueError:
        cut = max(1, round(len(weekly) / 2))
    cut = max(1, min(len(weekly) - 1, cut))

    antes = totals[:cut]
    depois = totals[cut:]
    media_antes = round(sum(antes) / len(antes), 2) if antes else 0
    media_depois = round(sum(depois) / len(depois), 2) if depois else 0
    n = min(len(antes), len(depois))
    comp_antes = sum(antes[len(antes) - n:]) if n else 0
    comp_depois = sum(depois[:n]) if n else 0
    ganho_pct = round((media_depois / media_antes - 1) * 100, 1) if media_antes > 0 else None
    fator = round(comp_depois / comp_antes, 2) if comp_antes > 0 else None

    return {
        "project_key": project_key,
        "cutoff_week": week_keys[cut],
        "cutoff_label": weekly[cut].get("week_label"),
        "cut_index": cut,
        "media_antes": media_antes,
        "media_depois": media_depois,
        "total_antes": sum(antes),
        "total_depois": sum(depois),
        "janela_semanas": n,
        "comp_antes": comp_antes,
        "comp_depois": comp_depois,
        "ganho_pct": ganho_pct,
        "fator": fator,
    }


@router.get("/api/metrics/wave2/forecast")
def api_forecast(project_key: str, remaining_items: int, simulations: int = 10000, history_weeks: int = 12):
    """Monte Carlo Forecast: estima semanas para concluir N itens restantes."""
    if remaining_items <= 0:
        return {"error": "remaining_items deve ser > 0"}
    conn = get_db_connection()
    result = monte_carlo_forecast(conn, project_key, remaining_items, simulations, history_weeks)
    conn.close()
    return result


@router.get("/api/metrics/wave2/open-epics")
def api_open_epics(project_key: str):
    """Retorna épicos/parents abertos com contagem de itens restantes."""
    conn = get_db_connection()
    result = get_open_epics(conn, project_key)
    conn.close()
    return {"project_key": project_key, "epics": result}


@router.get("/api/metrics/wave2/aging-backlog")
def api_aging_backlog(project_key: str, min_days: int = 30):
    """Retorna issues inativas há mais de N dias (candidatas a cancelamento)."""
    conn = get_db_connection()
    result = get_aging_backlog(conn, project_key, min_days)
    conn.close()
    return result
