"""Estáticos com allowlist.

Antes, StaticFiles(directory=BASE_DIR) servia QUALQUER arquivo da pasta do
projeto (issues.db, projects.yaml, código .py, .venv, .env...). Agora só é
servido o que o frontend realmente usa:
  - arquivos na raiz com extensão permitida (.html .css .js e imagens/fontes);
  - o mesmo dentro das pastas web listadas em WEB_DIRS;
  - nada que comece com "." (.env, .git, .venv).
Fase 5: WEB_DIRS passará a vir dos manifests dos módulos.
"""
from __future__ import annotations

import os

from fastapi import HTTPException
from starlette.staticfiles import StaticFiles

ALLOWED_EXT = {
    ".html", ".css", ".js",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".woff", ".woff2", ".ttf",
}
WEB_DIRS = {"hierarchy"}


def is_allowed(path: str) -> bool:
    p = path.replace("\\", "/").strip("/")
    if p in ("", "."):
        return True  # raiz (index.html); o Starlette passa "." para a raiz
    parts = p.split("/")
    if any(s == "" or s.startswith(".") for s in parts):
        return False
    if len(parts) == 1 and parts[0] in WEB_DIRS:
        return True  # índice da pasta web
    if len(parts) > 1 and parts[0] not in WEB_DIRS:
        return False
    return os.path.splitext(parts[-1])[1].lower() in ALLOWED_EXT


class SafeStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        if not is_allowed(path):
            raise HTTPException(status_code=404)
        return await super().get_response(path, scope)
