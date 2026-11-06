"""Configuração do módulo FLOW: a chave `projects` do projects.yaml."""
from __future__ import annotations

from typing import Any, Callable

from kernel.config_store import Section, get_store


def section() -> Section:
    return get_store().section("flow", owns=("projects",))


def load_projects(only_enabled: bool = True) -> list[dict]:
    projects = section().get("projects", []) or []
    return [p for p in projects if p.get("enabled", True)] if only_enabled else list(projects)


def update_projects(mutator: Callable[[list], Any]) -> Any:
    """mutator(lista) altera a lista IN PLACE (ou levanta exceção p/ abortar sem gravar)."""
    def _m(sub: dict):
        projects = sub.get("projects") or []
        result = mutator(projects)
        sub["projects"] = projects
        return result
    return section().update(_m)
