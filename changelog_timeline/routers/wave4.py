from metrics.wave4_portfolio import get_benchmarking
from metrics.wave4_portfolio import get_cross_project_throughput
from metrics.wave4_portfolio import get_epic_health
from core.db import get_db_connection
from routers.projects import _configured_project_keys
from fastapi import APIRouter

router = APIRouter()


# --- Wave 4: Cross-time e Portfólio ---


@router.get("/api/metrics/wave4/epic-health")
def api_epic_health(project_key: str):
    """Retorna saúde de cada épico (progresso, forecast, risco)."""
    conn = get_db_connection()
    result = get_epic_health(conn, project_key)
    conn.close()
    return result


@router.get("/api/metrics/wave4/benchmarking")
def api_benchmarking():
    """Retorna comparação de métricas entre os projetos CADASTRADOS (projects.yaml)."""
    conn = get_db_connection()
    result = get_benchmarking(conn, allowed_keys=_configured_project_keys())
    conn.close()
    return result


@router.get("/api/metrics/wave4/cross-project-throughput")
def api_cross_project_throughput(weeks: int = 26):
    """Retorna throughput semanal consolidado dos projetos CADASTRADOS (projects.yaml)."""
    conn = get_db_connection()
    result = get_cross_project_throughput(conn, weeks, allowed_keys=_configured_project_keys())
    conn.close()
    return result
