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
    from kernel.migrations import read_version
    v = read_version(DB_PATH)
    detail = f"{os.path.basename(DB_PATH)} · schema v{v}" if v is not None else f"{os.path.basename(DB_PATH)} · sem schema"
    return v is not None, detail


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
    home="/minha-visao.html",
    static_root=True,  # dono dos arquivos web da raiz (exceto assets da plataforma)
    nav=(
        NavItem("Minha Visão", "/minha-visao.html", "Minha Visão", 10, 10),
        NavItem("Compromisso", "/compromisso.html", "Prazos", 20, 10),
        NavItem("Previsibilidade", "/wave2.html", "Prazos", 20, 20),
        NavItem("Maturidade", "/maturidade.html", "Pessoas", 30, 10),
        NavItem("Pessoas", "/wave3.html", "Pessoas", 30, 20),
        NavItem("Gargalo e Fluxo", "/wave1.html", "Fluxo", 40, 10),
        NavItem("Portfólio", "/wave4.html", "Fluxo", 40, 20),
        NavItem("Dashboard", "/dashboard.html", "Fluxo", 40, 30),
        NavItem("Inconsistências", "/inconsistencies.html", "Dados", 60, 10),
        NavItem("Configurações", "/settings.html", "Dados", 60, 20),
    ),
    on_enable=_on_enable,
    health=_health,
)
