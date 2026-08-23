import uuid
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from starlette.responses import Response, JSONResponse
from starlette.requests import Request
import logfire

from app.config import settings


class GatewayCorrelationMiddleware(BaseHTTPMiddleware):
    """
    Unified Gateway Correlation Middleware.
    Extracts or generates X-Request-ID and sets it on request state and response headers.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract incoming or generate fresh UUID4
        incoming_req_id = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID")
        if incoming_req_id and len(incoming_req_id.strip()) > 3:
            req_id = incoming_req_id.strip()
        else:
            req_id = str(uuid.uuid4())

        request.state.request_id = req_id

        response = await call_next(request)

        response.headers["X-Request-ID"] = req_id
        response.headers["X-Correlation-ID"] = req_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Hardens HTTP response headers with defense-in-depth security standards.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        if settings.ENABLE_SECURITY_HEADERS:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
            response.headers["X-XSS-Protection"] = "1; mode=block"

        return response
