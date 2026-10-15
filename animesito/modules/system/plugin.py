"""The ``localguard`` plugin: what a single-user app on localhost still needs.

There is no login, so two browser-level attacks matter: a web page you visit
posting to http://127.0.0.1:7789 (CSRF), and DNS rebinding a hostile name onto
127.0.0.1 to read the API. The first is closed by requiring a custom header on
every state-changing request -- a cross-origin page cannot send one without a
CORS preflight, which the allow-list refuses. The second by refusing any Host
that is not one of ours.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from jfastframework.plugins.base import Plugin, PluginMeta, PluginSettings

if TYPE_CHECKING:
    from jfastframework.context import AppContext

CSRF_HEADER = "x-animesito"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class LocalGuardSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="JFAST_LOCALGUARD_", env_file=".env", extra="ignore"
    )

    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "[::1]", "testserver", "test"]
    )
    require_header: bool = True
    # Probes and the framework's own endpoints stay reachable without it.
    exempt_prefixes: list[str] = Field(
        default_factory=lambda: ["/health", "/ready", "/info", "/metrics", "/docs", "/openapi.json"]
    )


class LocalGuardMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: LocalGuardSettings) -> None:
        super().__init__(app)
        self.hosts = {host.lower() for host in settings.allowed_hosts}
        self.require_header = settings.require_header
        self.exempt = tuple(settings.exempt_prefixes)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        host = request.headers.get("host", "").lower()
        hostname = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
        if hostname not in self.hosts:
            return JSONResponse({"title": "Host not allowed", "status": 400}, status_code=400)
        if (
            self.require_header
            and request.method not in SAFE_METHODS
            and not request.url.path.startswith(self.exempt)
            and request.headers.get(CSRF_HEADER) != "1"
        ):
            return JSONResponse(
                {"title": f"Missing {CSRF_HEADER} header", "status": 403}, status_code=403
            )
        return await call_next(request)


class LocalGuardPlugin(Plugin):
    meta = PluginMeta(
        name="localguard",
        version="0.1.0",
        description="Host allow-list and CSRF header for a login-less local app.",
    )
    Settings = LocalGuardSettings

    def register(self, ctx: AppContext) -> None:
        ctx.app.add_middleware(LocalGuardMiddleware, settings=self.settings)
