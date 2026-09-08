import datetime as dt
import os
from typing import Any, List

from fastapi import FastAPI, HTTPException, Request
from starlette.middleware.cors import CORSMiddleware

from restmcp.logging import Logger

_rest_logger = Logger("restmcp.rest")


def _package_version() -> str:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version("restmcp")
    except PackageNotFoundError:
        return "0.0.0"


def serves_mcp(handler) -> bool:
    """Single source of the expose filter: is this handler part of the MCP
    surface? Used by both the /mcp/tools catalog and Server.mcp_handlers so
    the two can never disagree."""
    return getattr(handler, "expose", "both") != "rest"


def _auth_dependency(request: Request):
    if not os.getenv("AUTH_API_KEY"):
        return
    from restmcp.auth import current_auth, match_token, token_from_authorization

    token = token_from_authorization(request.headers.get("Authorization") or "")
    principal = match_token(token) if token else None
    if principal is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # Starlette convention: request.state.auth; plus the contextvar, which
    # run_callback carries into sync callbacks (issues #15/#16).
    request.scope.setdefault("state", {})["auth"] = principal
    current_auth.set(principal)


class RestApp:
    """FastAPI application with CORS, auth dependency, and default routes (/health, /mcp/tools)."""

    def __init__(self):
        self.app = FastAPI()
        # Rotas raw_response (issue #18): o FastAPI injeta um bloco de sucesso
        # automático em TODA operação do OpenAPI e não há como suprimi-lo por
        # rota — a poda vive aqui, no dono do documento. As rotas se inscrevem
        # em app.state.raw_routes ao registrar (endpoint.py); o pop é idempotente
        # sobre o schema cacheado.
        _openapi_original = self.app.openapi

        def _openapi_sem_sucesso_automatico_nas_cruas():
            schema = _openapi_original()
            for path, method in getattr(self.app.state, "raw_routes", ()):
                operacao = schema.get("paths", {}).get(path, {}).get(method)
                if operacao:
                    operacao.get("responses", {}).pop("200", None)
            return schema

        self.app.openapi = _openapi_sem_sucesso_automatico_nas_cruas
        # Issue #11: absent used to default to "*" (any origin, silently) and
        # empty produced allow_origins=[""] (blocks everything, silently, and
        # looks like a front-end bug). Safe default is DENY, loudly:
        raw = os.getenv("CORS_ORIGINS")
        cors_origins = [o.strip() for o in raw.split(",") if o.strip()] if raw else []
        if raw is None:
            _rest_logger.warning(
                "CORS_ORIGINS not set — cross-origin browser requests are denied. "
                "Set CORS_ORIGINS (e.g. 'https://app.example.com' or '*') to allow."
            )
        elif not cors_origins:
            _rest_logger.warning(
                "CORS_ORIGINS is set but contains no origin (%r) — cross-origin "
                "requests are denied. Did you mean CORS_ORIGINS='*'?", raw
            )
        if cors_origins:
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=cors_origins,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        self.url_handlers: List[Any] = []
        self._setup_default_routes()

    def _setup_default_routes(self):
        @self.app.get("/mcp/tools")
        def list_tools():
            return {
                "tools": [
                    {
                        "name": h.mcp_definition["name"],
                        "description": h.mcp_definition["description"],
                        # .get: a hand-written definition may omit
                        # parameters (validation allows it) — one such
                        # endpoint must not 500 the whole catalog.
                        "parameters": h.mcp_definition.get("parameters")
                        or {"properties": {}},
                        "returns": h.mcp_definition.get("returns", {}),
                    }
                    # the catalog advertises the MCP surface (serves_mcp —
                    # the same predicate Server.mcp_handlers uses)
                    for h in self.url_handlers
                    if serves_mcp(h)
                ],
                "server": "restmcp",
                "version": _package_version(),
            }

        @self.app.get("/health")
        def health_check():
            return {
                "status": "healthy",
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            }

    def register_handler(self, handler: Any):
        self.url_handlers.append(handler)

    def unregister_handler(self, handler: Any):
        if handler in self.url_handlers:
            self.url_handlers.remove(handler)
