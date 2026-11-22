"""HTTP contract, validation, and operational-limit tests for the FastAPI adapter."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from apps.api import main as api_module
from apps.api.main import ApiSettings, create_app
from rubiks_cube_ai_toolkit.model import FaceletState, Move

SOLVED = FaceletState.solved().serialize()


def _client(**overrides: object) -> TestClient:
    values = {
        "cors_origins": ("https://cube.example",),
        "requests_per_minute": 120,
        "max_concurrent_solves": 2,
        "body_limit_bytes": 4096,
    }
    values.update(overrides)
    return TestClient(create_app(ApiSettings(**values)))  # type: ignore[arg-type]


def test_health_and_cors_are_explicit() -> None:
    client = _client()
    assert client.get("/health").json() == {
        "status": "ok",
        "service": "rubiks-cube-api",
    }
    approved = client.options(
        "/api/validate",
        headers={"Origin": "https://cube.example", "Access-Control-Request-Method": "POST"},
    )
    rejected = client.options(
        "/api/validate",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert approved.headers["access-control-allow-origin"] == "https://cube.example"
    assert "access-control-allow-origin" not in rejected.headers


def test_scramble_validate_apply_and_verify_contracts() -> None:
    client = _client()
    scrambled = client.post("/api/scramble", json={"length": 8, "seed": "api-test"})
    assert scrambled.status_code == 200
    data = scrambled.json()["data"]
    assert len(data["moves"]) == 8
    assert client.post("/api/validate", json={"state": data["state"]}).json()["ok"] is True

    applied = client.post("/api/apply", json={"state": SOLVED, "moves": "R"})
    expected = FaceletState.solved().apply_move(Move.R).serialize()
    assert applied.json()["data"]["state"] == expected
    verified = client.post("/api/verify", json={"state": expected, "moves": "R'"})
    assert verified.json()["data"]["verified"] is True


def test_invalid_requests_are_strict_and_structured() -> None:
    client = _client()
    coercion = client.post("/api/scramble", json={"length": "20"})
    extra = client.post("/api/validate", json={"state": SOLVED, "unexpected": True})
    invalid_state = client.post("/api/validate", json={"state": "U" * 54})
    invalid_moves = client.post("/api/apply", json={"state": SOLVED, "moves": "X"})
    assert coercion.status_code == 422
    assert extra.json()["error"]["code"] == "INVALID_INPUT"
    assert invalid_state.status_code == 422
    assert invalid_state.json()["error"]["code"] == "INVALID_STATE"
    assert invalid_moves.json()["error"]["code"] == "INVALID_MOVES"


def test_request_size_and_rate_limits() -> None:
    size_client = _client(body_limit_bytes=512)
    oversized = size_client.post(
        "/api/apply",
        content=b"{" + b"x" * 600 + b"}",
        headers={"Content-Type": "application/json"},
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "REQUEST_TOO_LARGE"

    rate_client = _client(requests_per_minute=1)
    assert rate_client.post("/api/validate", json={"state": SOLVED}).status_code == 200
    limited = rate_client.post("/api/validate", json={"state": SOLVED})
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"


def test_solve_requires_independent_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    def unverified(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "ok": True,
            "tool": "cube_solve",
            "data": {"success": True, "verification": None},
            "error": None,
        }

    monkeypatch.setattr(api_module, "cube_solve", unverified)
    response = _client().post("/api/solve", json={"state": SOLVED})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "VERIFICATION_FAILED"


def test_solve_concurrency_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow_verified(*_args: object, **_kwargs: object) -> dict[str, object]:
        time.sleep(0.2)
        return {
            "ok": True,
            "tool": "cube_solve",
            "data": {"success": True, "verification": {"verified": True}},
            "error": None,
        }

    monkeypatch.setattr(api_module, "cube_solve", slow_verified)
    client = _client(max_concurrent_solves=1)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(client.post, "/api/solve", json={"state": SOLVED})
        time.sleep(0.05)
        second = client.post("/api/solve", json={"state": SOLVED})
        assert first.result().status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "SOLVER_BUSY"
