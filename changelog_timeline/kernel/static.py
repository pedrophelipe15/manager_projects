"""Estáticos por módulo, com allowlist.

Regras (URLs inalteradas; só passa a valer quem está ligado):
  - ASSETS DA PLATAFORMA (design system + menu): sempre servidos;
  - pasta web de um módulo (ex.: /hierarchy/...): só se o módulo está LIGADO (senão 404);
  - demais arquivos da raiz: só se um módulo "dono da raiz" (flow) está ligado;
  - só extensões web conhecidas; nada que comece com "." (.env, .git, .venv);
  - código, bancos, yaml, docs etc. nunca são servidos.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException
from starlette.staticfiles import StaticFiles

ALLOWED_EXT = {
    ".html", ".css", ".js",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".woff", ".woff2", ".ttf",
}

# Design system e menu: usados por TODOS os módulos (sempre disponíveis).
# dashboard.css entra aqui porque a hierarquia (pendencias.html) também o usa.
PLATFORM_ASSETS = frozenset({
    "tokens.css", "nav.css", "nav.js", "ui.css", "ui.js", "context.js", "dashboard.css",
})


@dataclass(frozen=True)
class StaticPolicy:
    dirs: frozenset = frozenset()   # pastas web de módulos ligados
    root: bool = False              # há módulo ligado dono da raiz?


def is_allowed(path: str, policy: StaticPolicy) -> bool:
    p = path.replace("\\", "/").strip("/")
    if p in ("", "."):
        return policy.root  # raiz/index.html pertence ao dono da raiz
    parts = p.split("/")
    if any(s == "" or s.startswith(".") for s in parts):
        return False
    if len(parts) == 1 and parts[0] in policy.dirs:
        return True  # índice da pasta web do módulo
    if os.path.splitext(parts[-1])[1].lower() not in ALLOWED_EXT:
        return False
    if len(parts) == 1:
        return parts[0] in PLATFORM_ASSETS or policy.root
    return parts[0] in policy.dirs


class SafeStaticFiles(StaticFiles):
    def __init__(self, *args, policy: Callable[[], StaticPolicy], **kwargs):
        super().__init__(*args, **kwargs)
        self._policy = policy

    async def get_response(self, path, scope):
        if not is_allowed(path, self._policy()):
            raise HTTPException(status_code=404)
        return await super().get_response(path, scope)
