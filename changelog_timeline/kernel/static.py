"""Estáticos: cada módulo serve a PRÓPRIA pasta web; a plataforma serve kernel/web.

Layout físico (URLs inalteradas):
  kernel/web/                 -> "/"           assets da plataforma (design system, menu, painel): sempre
  modules/<id>/web/           -> "/<prefixo>/" módulo com `web_prefix` (ex.: hierarchy -> /hierarchy/...)
  modules/<id>/web/           -> "/"           módulo "dono da raiz" (web_prefix vazio, ex.: flow)

Módulo desligado não é montado => suas páginas dão 404 (nada de política em runtime).
Defesa extra: só extensões web conhecidas e nada que comece com "." (.env, .git, .venv).
Código, bancos, yaml e docs ficam fora das pastas web, então nunca são alcançáveis.
"""
from __future__ import annotations

import os

from fastapi import HTTPException
from starlette.staticfiles import StaticFiles

KERNEL_WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

ALLOWED_EXT = {
    ".html", ".css", ".js",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".woff", ".woff2", ".ttf",
}


def is_allowed(path: str) -> bool:
    p = path.replace("\\", "/").strip("/")
    if p in ("", "."):
        return True  # raiz da pasta (index.html, se existir)
    parts = p.split("/")
    if any(s == "" or s.startswith(".") for s in parts):
        return False
    last = parts[-1]
    # diretórios (sem extensão) são tratados pelo StaticFiles (index.html / 404)
    return os.path.splitext(last)[1] == "" or os.path.splitext(last)[1].lower() in ALLOWED_EXT


class SafeStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        if not is_allowed(path):
            raise HTTPException(status_code=404)
        return await super().get_response(path, scope)


def mount_static(app, modules) -> None:
    """Monta os estáticos dos módulos LIGADOS. Chamar por último (não sombrear /api/*)."""
    for m in modules:
        if m.web_dir and m.web_prefix:
            app.mount("/" + m.web_prefix.strip("/"),
                      SafeStaticFiles(directory=m.web_dir, html=True), name=f"static-{m.id}")
    root = SafeStaticFiles(directory=KERNEL_WEB_DIR, html=True)
    for m in modules:
        if m.web_dir and not m.web_prefix:
            root.all_directories.append(m.web_dir)  # kernel/web vem primeiro: assets da plataforma têm prioridade
    app.mount("/", root, name="static")
