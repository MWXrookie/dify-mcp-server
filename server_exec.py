"""Optional code-execution variant.

This is intentionally not the default deployment. It executes arbitrary Python
inside a subprocess and must only be exposed on a trusted, isolated network.
"""

import os
import subprocess
import sys
from typing import Any

from fastmcp import FastMCP

try:
    from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
except ImportError:
    from fastmcp.server.auth import StaticTokenVerifier


token = os.environ.get("MCP_AUTH_TOKEN")
if not token or len(token) < 32:
    raise RuntimeError("MCP_AUTH_TOKEN must be set and at least 32 characters long")

auth = StaticTokenVerifier(
    tokens={token: {"client_id": "dify-code", "scopes": ["mcp:code"]}},
    required_scopes=["mcp:code"],
)
mcp = FastMCP("Dify Code Tools", auth=auth)


@mcp.tool
def run_python(code: str, timeout_seconds: int = 5) -> dict[str, Any]:
    """Execute a short Python snippet in a subprocess (trusted deployments only)."""
    if not 1 <= timeout_seconds <= 15:
        raise ValueError("timeout_seconds must be between 1 and 15")
    if len(code) > 4000:
        raise ValueError("code is limited to 4000 characters")
    completed = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd="/tmp",
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONUNBUFFERED": "1"},
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
    }


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=8001,
        path="/mcp",
        stateless_http=True,
    )
