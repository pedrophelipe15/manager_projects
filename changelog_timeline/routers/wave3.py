from metrics.wave3_people import get_handoff_time
from metrics.wave3_people import get_rework_rate
from metrics.wave3_people import get_wip_per_person
from metrics.wave3_people import get_workload_distribution
from core.db import get_db_connection
from fastapi import APIRouter

router = APIRouter()


# --- Wave 3: Pessoas e Qualidade ---


@router.get("/api/metrics/wave3/wip")
def api_wip_per_person(project_key: str):
    """Retorna WIP (issues ativas) por pessoa."""
    conn = get_db_connection()
    result = get_wip_per_person(conn, project_key)
    conn.close()
    return result


@router.get("/api/metrics/wave3/workload")
def api_workload(project_key: str, weeks: int = 12):
    """Retorna distribuição de carga (entregas por pessoa nas últimas N semanas)."""
    conn = get_db_connection()
    result = get_workload_distribution(conn, project_key, weeks)
    conn.close()
    return result


@router.get("/api/metrics/wave3/handoff")
def api_handoff(project_key: str):
    """Retorna análise de handoffs (mudanças de assignee) do projeto."""
    conn = get_db_connection()
    result = get_handoff_time(conn, project_key)
    conn.close()
    return result


@router.get("/api/metrics/wave3/rework")
def api_rework(project_key: str):
    """Retorna taxa de retrabalho (transições para trás no fluxo)."""
    conn = get_db_connection()
    result = get_rework_rate(conn, project_key)
    conn.close()
    return result
