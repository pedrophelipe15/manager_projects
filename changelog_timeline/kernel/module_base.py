"""Contrato de um módulo da plataforma.

Cada módulo (modules/<id>/module.py) expõe um objeto `module = Module(...)`
descrevendo o que ele traz. O kernel nunca importa módulos diretamente: só
através do registry, a partir de config/modules.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass(frozen=True)
class NavItem:
    """Item do menu principal. Itens com o mesmo `group` aparecem juntos."""
    label: str
    href: str
    group: str = ""            # nome do grupo no menu (vazio => grupo próprio com o nome do módulo)
    group_order: int = 100     # posição do grupo no menu (menor primeiro)
    order: int = 100           # posição do item dentro do grupo


@dataclass
class Module:
    id: str
    name: str
    version: str = "1.0.0"
    # ids de módulos que precisam estar ligados (e carregados) antes deste
    requires: tuple[str, ...] = ()
    # caminhos "pacote.modulo" cujo atributo `router` (APIRouter) será incluído
    routers: tuple[str, ...] = ()
    nav: tuple[NavItem, ...] = ()
    # URL de entrada do módulo (usada pela rota "/" do kernel)
    home: str = ""
    # pastas web (primeiro segmento da URL) que pertencem ao módulo; 404 se desligado
    static_dirs: tuple[str, ...] = ()
    # True se o módulo é dono dos arquivos web da RAIZ (exceto os assets da plataforma)
    static_root: bool = False
    # chamado uma vez ao ligar o módulo (criar banco/tabelas etc.)
    on_enable: Optional[Callable[[], None]] = None
    on_disable: Optional[Callable[[], None]] = None
    # retorna (ok, detalhe) — usado pelo status
    health: Optional[Callable[[], tuple[bool, str]]] = None


@dataclass
class ModuleStatus:
    id: str
    state: str  # "enabled" | "disabled" | "failed"
    name: str = ""
    version: str = ""
    error: Optional[str] = None
    requires: tuple[str, ...] = ()
    nav: tuple[NavItem, ...] = field(default_factory=tuple)
    home: str = ""
