from modules.flow.metrics.insights import run_insights
from modules.flow.db import get_db_connection
from fastapi import APIRouter

router = APIRouter()


# --- Insights ---


@router.get("/api/insights")
def api_insights(project_key: str):
    """Retorna análise automática de métricas — insights categorizados por severidade."""
    conn = get_db_connection()
    result = run_insights(conn, project_key)
    conn.close()
    return result


@router.get("/api/insights/alert-count")
def api_alert_count():
    """Retorna contagem total de alertas proativos de todos os projetos (para badge na nav)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT project_key FROM issues WHERE project_key IS NOT NULL")
    projects = [row[0] for row in cursor.fetchall()]

    total_alerts = 0
    critical_alerts = 0
    for pk in projects:
        result = run_insights(conn, pk)
        for insight in result.get("insights", []):
            if insight.get("category") == "alert":
                total_alerts += 1
                if insight.get("severity") == "critical":
                    critical_alerts += 1

    conn.close()
    return {"total": total_alerts, "critical": critical_alerts}
