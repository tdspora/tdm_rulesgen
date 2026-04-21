from __future__ import annotations

import logging
from http import HTTPStatus

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from rulesgen.api.problem_details import problem_response

logger = logging.getLogger("rulesgen.errors")


class ExceptionMappingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        try:
            await self.app(scope, receive, send)
        except Exception:  # noqa: BLE001
            logger.exception(
                "unhandled_exception",
                extra={
                    "request_id": getattr(request.state, "request_id", None),
                    "path": str(request.url.path),
                    "method": request.method,
                },
            )
            response = problem_response(
                request,
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="internal_server_error",
                title="Internal Server Error",
                detail="The server could not complete the request.",
            )
            await response(scope, receive, send)
