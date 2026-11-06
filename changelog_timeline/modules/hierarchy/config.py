"""Configuração do módulo HIERARCHY: chaves `hierarchy` e `excluded_projects` do projects.yaml."""
from __future__ import annotations

from typing import Any, Callable

from kernel.config_store import Section, get_store


def section() -> Section:
    return get_store().section("hierarchy", owns=("hierarchy", "excluded_projects"))


def load_entries() -> list[dict]:
    return list(section().get("hierarchy", []) or [])


def load_excluded_raw() -> list:
    return list(section().get("excluded_projects", []) or [])


def update_entries(mutator: Callable[[list], Any]) -> Any:
    """mutator(lista) altera a lista IN PLACE (ou levanta exceção p/ abortar sem gravar)."""
    def _m(sub: dict):
        entries = sub.get("hierarchy") or []
        result = mutator(entries)
        sub["hierarchy"] = entries
        return result
    return section().update(_m)


def update_excluded(mutator: Callable[[list], Any]) -> Any:
    def _m(sub: dict):
        keys = sub.get("excluded_projects") or []
        result = mutator(keys)
        sub["excluded_projects"] = keys
        return result
    return section().update(_m)
