"""Manifest do módulo HIERARCHY (Iniciativa -> Épico -> Story).

Fase 1: o manifest apenas aponta para os routers que já existem em routers/.
Limitações conhecidas (tratadas em fases futuras):
  - fase 4: routers de hierarquia ainda importam constantes de routers.projects (flow);
  - fase 5: os estáticos /hierarchy/* continuam servidos mesmo com o módulo desligado.
"""
from kernel.module_base import Module, NavItem


def _on_enable():
    # Fase 2: cria/atualiza o hierarchy.db por migrações — só se o módulo está ligado.
    from modules.hierarchy.schema import migrate_hierarchy
    migrate_hierarchy()


def _health():
    import os
    from modules.hierarchy.db import HIERARCHY_DB_PATH
    return os.path.exists(HIERARCHY_DB_PATH), HIERARCHY_DB_PATH


module = Module(
    id="hierarchy",
    name="Hierarquia",
    version="1.0.0",
    routers=(
        "routers.hierarchy_config",
        "routers.hierarchy_tree",
        "routers.hierarchy_sync",
        "routers.hierarchy_health",
    ),
    nav=(NavItem("Hierarquia", "/hierarchy/dashboard-v2.html", 20),),
    on_enable=_on_enable,
    health=_health,
)
