"""Registry de módulos: lê config/modules.yaml, carrega só os módulos ligados,
valida dependências e isola falhas (um módulo com erro não derruba os demais).

Ligar/desligar = editar config/modules.yaml e reiniciar (decisão D1, opção A).
"""
from __future__ import annotations

import importlib
import os
from typing import Optional

import yaml
from fastapi import APIRouter

from kernel.module_base import Module, ModuleStatus, NavItem

# Itens de menu da PRÓPRIA plataforma (existem mesmo sem nenhum módulo ligado).
PLATFORM_NAV = (NavItem("Módulos", "/modules.html", "Plataforma", 90, 10),)

DEFAULT_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "modules.yaml"
)


def load_config(path: Optional[str] = None) -> dict[str, bool]:
    """Retorna {module_id: enabled}, na ordem do arquivo.

    Arquivo ausente ou inválido => erro explícito (não assume nada em silêncio).
    """
    path = path or os.environ.get("MANAGER_MODULES_FILE") or DEFAULT_CONFIG
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw = data.get("modules")
    if not isinstance(raw, dict) or not raw:
        raise ValueError(f"{path}: chave 'modules' ausente ou vazia")
    out: dict[str, bool] = {}
    for mid, cfg in raw.items():
        if not isinstance(mid, str):
            # YAML 1.1 lê on/off/yes/no/null sem aspas como booleano/None
            raise ValueError(f"{path}: id de módulo inválido ({mid!r}); coloque entre aspas se for on/off/yes/no")
        enabled = cfg.get("enabled", True) if isinstance(cfg, dict) else bool(cfg)
        out[str(mid)] = bool(enabled)
    return out


class Registry:
    def __init__(self, config: dict[str, bool], package: str = "modules"):
        self.config = config
        self.package = package
        self.status: dict[str, ModuleStatus] = {}
        self.modules: dict[str, Module] = {}
        self.routers: list[tuple[str, APIRouter]] = []  # (module_id, router) na ordem de carga

    # ------------------------------------------------------------------
    def load(self) -> "Registry":
        for mid, enabled in self.config.items():
            if not enabled:
                self.status[mid] = ModuleStatus(id=mid, state="disabled")
        for mid, enabled in self.config.items():
            if enabled:
                self._load_one(mid, stack=())
        return self

    def _fail(self, mid: str, error: str, module: Optional[Module] = None) -> None:
        self.status[mid] = ModuleStatus(
            id=mid, state="failed", error=error,
            name=module.name if module else "", version=module.version if module else "",
            requires=module.requires if module else (),
        )

    def _load_one(self, mid: str, stack: tuple[str, ...]) -> bool:
        st = self.status.get(mid)
        if st is not None:
            return st.state == "enabled"
        if mid in stack:
            self._fail(mid, f"dependência circular: {' -> '.join(stack + (mid,))}")
            return False

        # 1. importa o manifest
        try:
            mod = importlib.import_module(f"{self.package}.{mid}.module")
            module: Module = mod.module
            if not isinstance(module, Module) or module.id != mid:
                raise TypeError(f"manifest inválido: esperado Module(id={mid!r})")
        except Exception as exc:  # noqa: BLE001 — isolamento é o objetivo
            self._fail(mid, f"falha ao importar manifest: {exc!r}")
            return False

        # 2. dependências
        for dep in module.requires:
            if not self.config.get(dep, False):
                self._fail(mid, f"requer o módulo '{dep}', que está desligado ou não existe", module)
                return False
            if not self._load_one(dep, stack + (mid,)):
                self._fail(mid, f"requer o módulo '{dep}', que falhou ao carregar", module)
                return False

        # 3. importa os routers ANTES de ligar (tudo ou nada)
        loaded: list[APIRouter] = []
        try:
            for path in module.routers:
                loaded.append(importlib.import_module(path).router)
        except Exception as exc:  # noqa: BLE001
            self._fail(mid, f"falha ao importar router: {exc!r}", module)
            return False

        # 4. on_enable
        try:
            if module.on_enable:
                module.on_enable()
        except Exception as exc:  # noqa: BLE001
            self._fail(mid, f"falha no on_enable: {exc!r}", module)
            return False

        self.modules[mid] = module
        self.routers.extend((mid, r) for r in loaded)
        self.status[mid] = ModuleStatus(
            id=mid, state="enabled", name=module.name, version=module.version,
            requires=module.requires, nav=module.nav, home=module.home,
        )
        return True

    # ------------------------------------------------------------------
    def home(self) -> str:
        """URL de entrada: a `home` do primeiro módulo ligado (ordem do modules.yaml)."""
        for mid in self.config:
            m = self.modules.get(mid)
            if m and m.home:
                return m.home
        return ""

    @staticmethod
    def _groups(nav) -> list[dict]:
        """Itens de um módulo agrupados: [{group, links:[{label, href}]}], ordenados."""
        groups: dict[str, dict] = {}
        for item in nav:
            g = groups.setdefault(item.group, {"order": item.group_order, "items": []})
            g["order"] = min(g["order"], item.group_order)
            g["items"].append(item)
        out = []
        for name, g in sorted(groups.items(), key=lambda kv: (kv[1]["order"], kv[0])):
            items = sorted(g["items"], key=lambda i: (i.order, i.label))
            out.append({"group": name, "links": [{"label": i.label, "href": i.href} for i in items]})
        return out

    def menu(self) -> list[dict]:
        """Menu lateral: UM item por módulo (na ordem do modules.yaml), com as páginas dentro.

        Módulo ligado => seus grupos/links; módulo com falha => entrada marcada (sem links);
        módulo desligado => não aparece. A Plataforma vem sempre por último, fixa no rodapé.
        """
        out: list[dict] = []
        for mid in self.config:
            m = self.modules.get(mid)
            st = self.status.get(mid)
            if m:
                out.append({"id": mid, "name": m.name, "icon": m.icon or "grid", "state": "enabled",
                            "pinned": False, "home": m.home, "groups": self._groups(m.nav)})
            elif st and st.state == "failed":
                out.append({"id": mid, "name": st.name or mid, "icon": "alert", "state": "failed",
                            "pinned": False, "home": "", "groups": []})
        out.append({"id": "platform", "name": "Plataforma", "icon": "grid", "state": "enabled",
                    "pinned": True, "home": PLATFORM_NAV[0].href, "groups": self._groups(PLATFORM_NAV)})
        return out

    def describe(self) -> list[dict]:
        """Estado de todos os módulos configurados, com saúde dos ligados."""
        items = []
        for mid in self.config:
            st = self.status.get(mid)
            if st is None:
                continue
            health = None
            module = self.modules.get(mid)
            if st.state == "enabled" and module and module.health:
                try:
                    ok, detail = module.health()
                    health = {"ok": bool(ok), "detail": detail}
                except Exception as exc:  # noqa: BLE001
                    health = {"ok": False, "detail": repr(exc)}
            items.append({
                "id": st.id, "state": st.state, "name": st.name, "version": st.version,
                "error": st.error, "requires": list(st.requires), "health": health,
                "home": st.home, "icon": (self.modules[st.id].icon if st.id in self.modules else ""),
                "nav": [{"label": n.label, "href": n.href, "group": n.group, "order": n.order}
                        for n in st.nav],
            })
        return items
