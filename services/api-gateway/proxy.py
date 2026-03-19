"""
HTTP reverse proxy for the API Gateway.

Validates the JWT from either the Authorization header or the access_token cookie,
then forwards the request to the appropriate downstream microservice.

Service map (first path segment → base URL):
  rfps       → rfp-service:8005
  ask        → orchestrator:8001
  documents  → content-service:8003
  admin      → analytics-service:8009
  products   → portfolio-service:8010
"""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from jose import JWTError

from auth import decode_token
from common.logging import get_logger

logger = get_logger("api-gateway.proxy")

_SERVICE_MAP: dict[str, str] = {
    "rfps": os.environ.get("RFP_SERVICE_URL", "http://rfp-service:8005"),
    "ask": os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8001"),
    "documents": os.environ.get("CONTENT_SERVICE_URL", "http://content-service:8003"),
    "admin": os.environ.get("ANALYTICS_SERVICE_URL", "http://analytics-service:8009"),
    "products": os.environ.get("PORTFOLIO_SERVICE_URL", "http://portfolio-service:8010"),
}

router = APIRouter(tags=["proxy"])

_SKIP_HEADERS = {"host", "content-length", "transfer-encoding"}


def _extract_token(request: Request) -> str | None:
    """Pull JWT from Authorization header or access_token cookie."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("access_token")


def _require_valid_token(request: Request) -> None:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.api_route("/{full_path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE"])
async def proxy(request: Request, full_path: str) -> Response:
    """JWT-authenticated reverse proxy to downstream microservices."""
    _require_valid_token(request)

    # Route on the first path segment
    segments = full_path.split("/", 1)
    service = segments[0]
    remainder = segments[1] if len(segments) > 1 else ""

    base_url = _SERVICE_MAP.get(service)
    if base_url is None:
        raise HTTPException(status_code=404, detail="Not Found")

    target_path = f"/{service}/{remainder}" if remainder else f"/{service}"
    target_url = f"{base_url}{target_path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _SKIP_HEADERS}

    # Ensure Authorization header is set (covers cookie-auth clients)
    token = _extract_token(request)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            upstream = await client.request(
                method=request.method,
                url=target_url,
                content=body,
                headers=headers,
            )
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type"),
        )
    except httpx.ConnectError:
        logger.warning(f"Service '{service}' unreachable at {base_url}")
        raise HTTPException(status_code=503, detail=f"Service '{service}' temporarily unavailable")
    except Exception as exc:
        logger.error(f"Proxy error for /{service}: {exc}")
        raise HTTPException(status_code=502, detail="Upstream error")
