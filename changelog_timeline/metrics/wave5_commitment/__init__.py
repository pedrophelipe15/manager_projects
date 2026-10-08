"""Wave 5: Compromisso de Prazo (Due Date Commitment).

Responde a pergunta nº1 dos gestores: a equipe cumpre prazo ou so empurra a
data pra frente? Consome parsed_changelogs WHERE field='duedate'.

Sub-metricas:
  5.1 Due Date Slippage  -> reprogramacoes por issue (persiste tabela)
  5.2 Commitment Score   -> agregacoes on-read por projeto e por assignee
"""

from .due_date_slippage import calculate_due_date_slippage, setup_table
from .commitment_score import (
    get_slippage_by_project,
    get_commitment_summary_all,
)

__all__ = [
    "run_wave5",
    "calculate_due_date_slippage",
    "get_slippage_by_project",
    "get_commitment_summary_all",
]


def run_wave5(conn, only_keys=None) -> dict:
    """Executa as sub-metricas persistidas da Wave 5. Retorna contadores."""
    results = {}
    results["due_date_slippage"] = calculate_due_date_slippage(conn, only_keys)
    return results
