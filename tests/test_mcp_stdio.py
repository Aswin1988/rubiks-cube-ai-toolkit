"""End-to-end smoke test for the installed MCP stdio entry point."""

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SOLVED = "UUUUUUUUURRRRRRRRRFFFFFFFFFDDDDDDDDDLLLLLLLLLBBBBBBBBB"
TOOLS = {
    "cube_scramble",
    "cube_validate",
    "cube_apply",
    "cube_solve",
    "cube_verify",
}


def _payload(result: Any) -> dict[str, Any]:
    payload = result.structured_content
    assert isinstance(payload, dict), result
    assert payload.get("ok") is True, payload
    return payload


@pytest.mark.solver
def test_mcp_stdio_scramble_solve_verify_smoke() -> None:
    pytest.importorskip("rubik_solver")
    pytest.importorskip("psutil")
    executable = Path(sys.executable).with_name(
        "cube-ai-mcp.exe" if sys.platform == "win32" else "cube-ai-mcp"
    )
    assert executable.is_file(), f"MCP entry point not found: {executable}"

    async def smoke_test() -> None:
        server = StdioServerParameters(command=str(executable))
        async with (
            stdio_client(server) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            listed = await session.list_tools()
            assert {tool.name for tool in listed.tools} == TOOLS

            scrambled = _payload(
                await session.call_tool("cube_scramble", {"length": 5, "seed": "mcp-stdio-smoke"})
            )
            state = scrambled["data"]["state"]
            solved = _payload(await session.call_tool("cube_solve", {"state": state}))
            solution = " ".join(solved["data"]["moves"])
            verified = _payload(
                await session.call_tool("cube_verify", {"state": state, "moves": solution})
            )

            assert verified["data"]["verified"] is True
            assert verified["data"]["final_state"] == SOLVED

    asyncio.run(smoke_test())
