"""Bounded HTTP transport for the existing verified Rubik's Cube operations."""

from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rubiks_cube_ai_toolkit.mcp_server import (
    cube_apply,
    cube_scramble,
    cube_solve,
    cube_validate,
    cube_verify,
)

MAX_BODY_BYTES = 4 * 1024


@dataclass(frozen=True, slots=True)
class ApiSettings:
    """Runtime limits and approved browser origins for the HTTP adapter."""

    cors_origins: tuple[str, ...] = ("http://localhost:3000",)
    requests_per_minute: int = 120
    max_concurrent_solves: int = 2
    body_limit_bytes: int = MAX_BODY_BYTES

    @classmethod
    def from_environment(cls) -> ApiSettings:
        """Read bounded settings from environment variables."""
        origins = tuple(
            origin.strip()
            for origin in os.getenv("CUBE_CORS_ORIGINS", "http://localhost:3000").split(",")
            if origin.strip()
        )
        return cls(
            cors_origins=origins,
            requests_per_minute=_bounded_environment_int(
                "CUBE_RATE_LIMIT_PER_MINUTE", default=120, minimum=1, maximum=10_000
            ),
            max_concurrent_solves=_bounded_environment_int(
                "CUBE_MAX_CONCURRENT_SOLVES", default=2, minimum=1, maximum=32
            ),
            body_limit_bytes=_bounded_environment_int(
                "CUBE_MAX_BODY_BYTES", default=MAX_BODY_BYTES, minimum=512, maximum=64 * 1024
            ),
        )


def _bounded_environment_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


class StrictRequest(BaseModel):
    """Base request that rejects coercion and unknown fields."""

    model_config = ConfigDict(strict=True, extra="forbid")


class ScrambleRequest(StrictRequest):
    """Inputs for deterministic or random scramble generation."""

    length: int = Field(default=20, ge=1, le=100)
    seed: str | int | None = Field(default=None)


class StateRequest(StrictRequest):
    """One canonical URFDLB facelet state."""

    state: str = Field(min_length=54, max_length=54)


class MovesRequest(StateRequest):
    """A state and a bounded Singmaster sequence."""

    moves: str = Field(max_length=512)


class SolveRequest(StateRequest):
    """A state and user-adjustable bounded solve limits."""

    timeout_seconds: float = Field(default=10.0, gt=0, le=30)
    max_moves: int = Field(default=30, ge=1, le=100)


class BodyLimitMiddleware:
    """Reject HTTP bodies after a strict byte bound, including chunked requests."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        content_length = next(
            (value for key, value in scope.get("headers", []) if key == b"content-length"),
            None,
        )
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    await _send_error(
                        scope, receive, send, 413, "REQUEST_TOO_LARGE", "request body is too large"
                    )
                    return
            except ValueError:
                await _send_error(
                    scope, receive, send, 400, "INVALID_REQUEST", "invalid Content-Length header"
                )
                return

        messages: list[Message] = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                return
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                await _send_error(
                    scope, receive, send, 413, "REQUEST_TOO_LARGE", "request body is too large"
                )
                return
            if not message.get("more_body", False):
                break

        async def replay() -> Message:
            if messages:
                return messages.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay, send)


async def _send_error(
    scope: Scope,
    receive: Receive,
    send: Send,
    status: int,
    code: str,
    message: str,
) -> None:
    response = JSONResponse(
        status_code=status,
        content={"ok": False, "data": None, "error": {"code": code, "message": message}},
    )
    await response(scope, receive, send)


class SlidingWindowLimiter:
    """Small in-process fixed-capacity limiter for a single API instance."""

    def __init__(self, requests_per_minute: int) -> None:
        self.limit = requests_per_minute
        self._requests: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allowed(self, key: str) -> bool:
        """Return whether a request is admitted in the current rolling minute."""
        now = time.monotonic()
        async with self._lock:
            entries = self._requests[key]
            while entries and entries[0] <= now - 60:
                entries.popleft()
            if len(entries) >= self.limit:
                return False
            entries.append(now)
            return True


def _client_key(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _http_status(payload: dict[str, object]) -> int:
    error = payload.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    return {
        "INVALID_INPUT": 422,
        "INVALID_STATE": 422,
        "INVALID_MOVES": 422,
        "NOT_SOLVED": 422,
        "TIMEOUT": 504,
        "RESOURCE_LIMIT": 503,
        "UNAVAILABLE": 503,
        "FAILURE": 502,
        "VERIFICATION_FAILED": 502,
    }.get(code, 400)


def _api_response(payload: dict[str, object]) -> JSONResponse:
    content = {"ok": payload["ok"], "data": payload["data"], "error": payload["error"]}
    return JSONResponse(
        status_code=200 if payload["ok"] else _http_status(payload), content=content
    )


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Create an isolated FastAPI application with bounded runtime state."""
    effective = settings or ApiSettings.from_environment()
    application = FastAPI(
        title="Rubik's Cube AI Toolkit API",
        version="0.4.0",
        docs_url=None,
        redoc_url=None,
    )
    application.add_middleware(BodyLimitMiddleware, max_bytes=effective.body_limit_bytes)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(effective.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
        max_age=600,
    )
    limiter = SlidingWindowLimiter(effective.requests_per_minute)
    solve_slots = asyncio.Semaphore(effective.max_concurrent_solves)

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
        details = [
            {"path": ".".join(str(part) for part in item["loc"]), "message": item["msg"]}
            for item in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "data": {"issues": details},
                "error": {"code": "INVALID_INPUT", "message": "request validation failed"},
            },
        )

    @application.middleware("http")
    async def rate_limit(request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        if request.url.path.startswith("/api/") and not await limiter.allowed(_client_key(request)):
            return JSONResponse(
                status_code=429,
                content={
                    "ok": False,
                    "data": None,
                    "error": {"code": "RATE_LIMITED", "message": "request rate limit exceeded"},
                },
                headers={"Retry-After": "60"},
            )
        return await call_next(request)

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "rubiks-cube-api"}

    @application.post("/api/scramble")
    async def scramble(request: ScrambleRequest) -> JSONResponse:
        return _api_response(cube_scramble(request.length, request.seed))

    @application.post("/api/validate")
    async def validate(request: StateRequest) -> JSONResponse:
        return _api_response(cube_validate(request.state))

    @application.post("/api/apply")
    async def apply(request: MovesRequest) -> JSONResponse:
        return _api_response(cube_apply(request.state, request.moves))

    @application.post("/api/verify")
    async def verify(request: MovesRequest) -> JSONResponse:
        return _api_response(cube_verify(request.state, request.moves))

    @application.post("/api/solve")
    async def solve(request: SolveRequest) -> JSONResponse:
        if solve_slots.locked():
            return JSONResponse(
                status_code=429,
                content={
                    "ok": False,
                    "data": None,
                    "error": {"code": "SOLVER_BUSY", "message": "all solver slots are busy"},
                },
                headers={"Retry-After": "1"},
            )
        async with solve_slots:
            payload = await asyncio.to_thread(
                cube_solve, request.state, request.timeout_seconds, request.max_moves
            )
        if payload["ok"]:
            data = payload.get("data")
            verification = data.get("verification") if isinstance(data, dict) else None
            if not isinstance(verification, dict) or verification.get("verified") is not True:
                payload = {
                    "ok": False,
                    "data": data,
                    "error": {
                        "code": "VERIFICATION_FAILED",
                        "message": "solver success lacked independent verification",
                    },
                }
        return _api_response(payload)

    return application


app = create_app()
