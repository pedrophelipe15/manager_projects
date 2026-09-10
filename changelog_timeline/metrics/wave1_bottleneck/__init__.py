"""Wave 1: Gargalo e Fluxo.
Sub-métricas:
  1.1 Tempo médio/P85 por status
  1.2 Percentis de Lead/Cycle Time
  1.3 Flow Efficiency
  1.4 Cumulative Flow Diagram (CFD)
  1.5 Aging WIP Report
"""

from ..changelog_cache import load_status_changelogs
from .time_per_status import calculate_time_per_status
from .percentiles import calculate_percentiles
from .flow_efficiency import calculate_flow_efficiency
from .cfd import calculate_cfd
from .aging_wip import calculate_aging_wip


def run_wave1(conn, only_keys=None) -> dict:
    """Executa todas as sub-métricas da Wave 1. Retorna contadores.
    
    Carrega changelogs de status UMA VEZ e compartilha entre todos os módulos.
    """
    # Limpa registros órfãos (issues que foram removidas do banco)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM metrics_per_status WHERE issue_key NOT IN (SELECT key FROM issues)")
    cursor.execute("DELETE FROM metrics_flow WHERE issue_key NOT IN (SELECT key FROM issues)")
    conn.commit()

    # Carrega cache de transições de status (1 query para todos os módulos)
    status_cache = load_status_changelogs(conn, only_keys)

    results = {}
    results["time_per_status"] = calculate_time_per_status(conn, only_keys, status_cache=status_cache)
    results["percentiles"] = calculate_percentiles(conn, only_keys)
    results["flow_efficiency"] = calculate_flow_efficiency(conn, only_keys, status_cache=status_cache)
    results["cfd"] = calculate_cfd(conn, only_keys, status_cache=status_cache)
    results["aging_wip"] = calculate_aging_wip(conn, only_keys)
    return results
