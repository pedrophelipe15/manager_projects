"""Manifest do módulo HIERARCHY (Iniciativa -> Épico -> Story).

Tudo do módulo mora aqui: routers/, metrics.py, db.py, config.py, migrations/ e web/
(servida em /hierarchy/...). Ligado/desligado em config/modules.yaml: desligado => sem rotas
/api/hierarchy/*, sem páginas /hierarchy/* (404), sem item no menu e sem criar o hierarchy.db.
"""
import os

from kernel.module_base import Module, NavItem


def _on_enable():
    # Fase 2: cria/atualiza o hierarchy.db por migrações — só se o módulo está ligado.
    from modules.hierarchy.schema import migrate_hierarchy
    migrate_hierarchy()


def _health():
    import os
    from kernel.migrations import read_version
    from modules.hierarchy.db import HIERARCHY_DB_PATH
    v = read_version(HIERARCHY_DB_PATH)
    name = os.path.basename(HIERARCHY_DB_PATH)
    detail = f"{name} · schema v{v}" if v is not None else f"{name} · sem schema"
    return v is not None, detail


module = Module(
    id="hierarchy",
    name="Hierarquia",
    version="1.0.0",
    routers=(
        "modules.hierarchy.routers.config",
        "modules.hierarchy.routers.tree",
        "modules.hierarchy.routers.sync",
        "modules.hierarchy.routers.health",
    ),
    home="/hierarchy/dashboard-v2.html",
    web_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "web"),
    web_prefix="hierarchy",  # servida em /hierarchy/...
    icon="tree",
    # as páginas que antes ficavam numa sub-navegação própria agora são itens do menu lateral
    nav=(
        NavItem("Dashboard", "/hierarchy/dashboard-v2.html", "", 10, 10),
        NavItem("Pendências", "/hierarchy/pendencias.html", "", 10, 20),
        NavItem("Roadmap", "/hierarchy/roadmap.html", "", 10, 30),
        NavItem("Timeline", "/hierarchy/timeline.html", "", 10, 40),
        NavItem("Configurações", "/hierarchy/settings.html", "", 10, 50),
    ),
    on_enable=_on_enable,
    health=_health,
)
