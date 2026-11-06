"""Manifest do módulo FLOW (dashboards de fluxo, Waves 1-5, insights, settings).

Fase 1: o manifest apenas aponta para os routers que já existem em routers/.
Os arquivos físicos serão movidos para modules/flow/ na fase 8.
"""
from kernel.module_base import Module, NavItem


def _on_enable():
    # Fase 2: cria/atualiza o issues.db por migrações versionadas (modules/flow/migrations).
    from modules.flow.schema import migrate_flow
    migrate_flow()


def _health():
    import os
    from core.db import DB_PATH
    return os.path.exists(DB_PATH), DB_PATH


module = Module(
    id="flow",
    name="Fluxo e Métricas",
    version="1.0.0",
    routers=(
        "routers.blacklist",
        "routers.issues",
        "routers.projects",
        "routers.purge",
        "routers.validations",
        "routers.inconsistencies",
        "routers.wave1",
        "routers.insights",
        "routers.wave2",
        "routers.wave5",
        "routers.home",
        "routers.wave3",
        "routers.wave4",
    ),
    nav=(NavItem("Minha Visão", "/minha-visao.html", 10),),
    on_enable=_on_enable,
    health=_health,
)
