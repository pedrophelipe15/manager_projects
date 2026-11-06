"""Monta a aplicação FastAPI: middleware, módulos ligados, rota de status e estáticos."""
from __future__ import annotations

import logging
import sys
from typing import Optional

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from kernel.paths import BASE_DIR
from kernel.registry import Registry, load_config
from kernel.static import mount_static

log = logging.getLogger("kernel")


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Desabilita cache em arquivos estáticos (dev)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


def create_app(modules_file: Optional[str] = None, package: str = "modules") -> FastAPI:
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)

    app = FastAPI(title="Manager Projects API")
    app.add_middleware(NoCacheMiddleware)

    registry = Registry(load_config(modules_file), package=package).load()
    app.state.registry = registry

    for st in registry.status.values():
        if st.state == "failed":
            log.error("módulo %s FALHOU: %s", st.id, st.error)

    # A ordem de inclusão preserva a ordem de registro das rotas.
    for _mid, router in registry.routers:
        app.include_router(router)

    kernel_router = APIRouter()

    @kernel_router.get("/api/platform/modules")
    def api_modules():
        """Estado dos módulos configurados (ligado/desligado/falhou) e seus itens de menu."""
        return {"modules": registry.describe(), "menu": registry.menu()}

    @kernel_router.get("/", include_in_schema=False)
    def root():
        """Entrada: leva à home do primeiro módulo ligado (antes servia o index.html do flow)."""
        home = registry.home()
        if home:
            return RedirectResponse(home)
        return HTMLResponse("<h1>Nenhum módulo ligado</h1><p>Edite config/modules.yaml e reinicie.</p>",
                            status_code=503)

    app.include_router(kernel_router)

    # Estáticos: SEMPRE por último, para não sombrear as rotas /api/*.
    mount_static(app, registry.modules.values())
    return app
