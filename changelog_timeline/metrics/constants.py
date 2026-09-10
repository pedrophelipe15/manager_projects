"""Constantes compartilhadas de fluxo — fonte única de verdade.

Centraliza os conjuntos de status "ativos" e a ordem lógica do fluxo, que antes
estavam duplicados (com risco de drift) em base.py, wave3_people/wip.py,
wave3_people/rework.py, wave4_portfolio/benchmarking.py e no api.py.
"""

from __future__ import annotations

# Estados em que o "relógio" de cycle time está rodando (trabalho ativo).
# Usado por metrics/base.py e pela agregação de hierarquia em api.py.
ACTIVE_STATES: set[str] = {"In Progress", "Blocked", "Test", "Waiting for Delivery"}

# Variante para WIP por pessoa (wave3/wip.py): Blocked NÃO conta como carga
# ativa da pessoa (é tratado à parte, de forma informativa). Mantido separado
# de ACTIVE_STATES de propósito — não unificar.
WIP_ACTIVE_STATES: set[str] = {"In Progress", "Test"}

# Ordem lógica dos status (do mais inicial para o mais avançado). Usada para
# detectar transições "para trás" (retrabalho).
STATUS_ORDER: dict[str, int] = {
    "Open": 0, "Backlog": 1, "To do": 2, "Refinement": 3,
    "In Progress": 4, "Blocked": 4, "Test": 5,
    "Waiting for Delivery": 6, "Done": 7,
}

# Ordem padrão atribuída a um status desconhecido (mantém o comportamento
# histórico das implementações originais).
_DEFAULT_STATUS_ORDER = 3


def is_backward_transition(from_value: str | None, to_value: str | None) -> bool:
    """True se a transição de status é "para trás" (retrabalho).

    Replica exatamente a lógica original: status desconhecido assume ordem 3,
    e a transição só conta como retrabalho quando ambos os valores existem e
    a ordem de destino é menor que a de origem.
    """
    if not from_value or not to_value:
        return False
    from_order = STATUS_ORDER.get(from_value, _DEFAULT_STATUS_ORDER)
    to_order = STATUS_ORDER.get(to_value, _DEFAULT_STATUS_ORDER)
    return to_order < from_order
