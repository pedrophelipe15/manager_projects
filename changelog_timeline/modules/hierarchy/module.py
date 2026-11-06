"""Manifest do módulo HIERARCHY (Iniciativa -> Épico -> Story).

Fase 1: o manifest apenas aponta para os routers que já existem em routers/.
Ligado/desligado em config/modules.yaml: desligado => sem rotas /api/hierarchy/*, sem
páginas /hierarchy/* (404), sem item no menu e sem criar o hierarchy.db.
Os arquivos físicos serão movidos para modules/hierarchy/ na fase 8.
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
    home="/hierarchy/dashboard-v2.html",
    static_dirs=("hierarchy",),
    nav=(NavItem("Hierarquia", "/hierarchy/dashboard-v2.html", "Hierarquia", 50, 10),),
    on_enable=_on_enable,
    health=_health,
)
