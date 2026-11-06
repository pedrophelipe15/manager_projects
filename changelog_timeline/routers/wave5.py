from metrics.wave5_commitment import get_commitment_summary_all
from metrics.wave5_commitment import get_slippage_by_project
from core.db import get_db_connection
from fastapi import APIRouter

router = APIRouter()


# --- Wave 5: Compromisso de Prazo (Due Date Commitment) ---


@router.get("/api/metrics/wave5/slippage")
def api_slippage(project_key: str):
    """Compromisso de prazo do projeto: commitment score, por assignee e piores issues.

    Responde a pergunta nº1 dos gestores: a equipe cumpre prazo ou so empurra?
    Consome a tabela metrics_due_date_slippage (populada na ingestão / Wave 5).
    """
    conn = get_db_connection()
    result = get_slippage_by_project(conn, project_key)
    conn.close()
    return result


@router.get("/api/metrics/wave5/commitment-summary")
def api_commitment_summary():
    """Resumo de commitment score por projeto (todos), para a home 'Minha Visão'."""
    conn = get_db_connection()
    result = get_commitment_summary_all(conn)
    conn.close()
    return result
