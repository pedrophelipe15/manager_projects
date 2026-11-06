"""Manifest do módulo FLOW (dashboards de fluxo, Waves 1-5, insights, settings).

Tudo do módulo mora aqui: routers/, metrics/, db.py, ingest.py, config.py, migrations/ e web/
(páginas servidas na raiz "/"). Atalho de CLI na raiz: ingest_to_db.py -> modules/flow/ingest.py.
"""
import os

from kernel.module_base import Module, NavItem


def _on_enable():
    # Fase 2: cria/atualiza o issues.db por migrações versionadas (modules/flow/migrations).
    from modules.flow.schema import migrate_flow
    migrate_flow()


def _health():
    import os
    from modules.flow.db import DB_PATH
    from kernel.migrations import read_version
    v = read_version(DB_PATH)
    detail = f"{os.path.basename(DB_PATH)} · schema v{v}" if v is not None else f"{os.path.basename(DB_PATH)} · sem schema"
    return v is not None, detail


module = Module(
    id="flow",
    name="Fluxo e Métricas",
    version="1.0.0",
    routers=(
        "modules.flow.routers.blacklist",
        "modules.flow.routers.issues",
        "modules.flow.routers.projects",
        "modules.flow.routers.purge",
        "modules.flow.routers.validations",
        "modules.flow.routers.inconsistencies",
        "modules.flow.routers.wave1",
        "modules.flow.routers.insights",
        "modules.flow.routers.wave2",
        "modules.flow.routers.wave5",
        "modules.flow.routers.home",
        "modules.flow.routers.wave3",
        "modules.flow.routers.wave4",
    ),
    home="/minha-visao.html",
    icon="chart",
    web_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "web"),  # servida na raiz "/"
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
