"""FastMCP gateway with fixed tools and a guarded internal code executor."""

import importlib.util
import json
import os
from typing import Any

import httpx
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

try:
    from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
except ImportError:
    from fastmcp.server.auth import StaticTokenVerifier

from library_tools import ALLOWED_TOOLS
from dashboard import init_db, record_execution, DASHBOARD_HTML, get_executions, get_stats


token = os.environ.get("MCP_AUTH_TOKEN")
executor_token = os.environ.get("EXECUTOR_SHARED_TOKEN")
deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY", "")
deepseek_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
max_retries_default = int(os.environ.get("CODE_RETRY_MAX", "7"))

if not token or len(token) < 32:
    raise RuntimeError("MCP_AUTH_TOKEN must be set and at least 32 characters long")
if not executor_token or len(executor_token) < 32:
    raise RuntimeError("EXECUTOR_SHARED_TOKEN must be set and at least 32 characters long")

auth = StaticTokenVerifier(
    tokens={token: {"client_id": "dify", "scopes": ["mcp:tools"]}},
    required_scopes=["mcp:tools"],
)
mcp = FastMCP("Dify JWave Tools", auth=auth)


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _clean_code(code: str) -> str:
    """去掉 LLM 输出中可能包裹的 markdown 代码块标记."""
    code = code.strip()
    for prefix in ("```python\n", "```python", "```\n", "```"):
        if code.startswith(prefix):
            code = code[len(prefix):]
    for suffix in ("\n```", "```"):
        if code.endswith(suffix):
            code = code[:-len(suffix)]
    return code.strip()


def _execute_code(code: str, timeout_seconds: int) -> dict[str, Any]:
    """提交代码到 jwave-executor 并返回执行结果."""
    response = httpx.post(
        "http://jwave-executor:8010/execute",
        headers={"X-Executor-Token": executor_token},
        json={"code": code, "timeout_seconds": timeout_seconds},
        timeout=timeout_seconds + 10,
    )
    response.raise_for_status()
    return response.json()


def _llm_fix_code(api_key: str, model: str, code: str, result: dict[str, Any]) -> str:
    """调用 DeepSeek API 修正出错的代码，返回修正后的代码字符串."""
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY must be set to use auto-fix")

    prompt = (
        "You are a Python debugging assistant. The following Python code was executed "
        "in a container with jwave, jax, jaxlib, jaxdf, equinox, and jaxtyping "
        "installed. JAX runs CPU-only. The code failed. Your job: return ONLY the "
        "corrected Python code. No markdown fences, no explanations — just raw, "
        "runnable Python.\n\n"
        "EXECUTION RESULT:\n"
        f"- exit_code: {result.get('exit_code')}\n"
        f"- timed_out: {result.get('timed_out')}\n"
        f"- stdout (last 3000 chars):\n{result.get('stdout', '')[-3000:]}\n"
        f"- stderr (last 3000 chars):\n{result.get('stderr', '')[-3000:]}\n"
        "\nFAILED CODE:\n"
        f"```python\n{code}\n```\n"
        "\nReturn ONLY the fixed Python code:"
    )

    llm_response = httpx.post(
        "https://api.deepseek.com/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 8000,
        },
        timeout=60,
    )
    llm_response.raise_for_status()
    data = llm_response.json()
    fixed = data["choices"][0]["message"]["content"].strip()

    # 去掉可能的 markdown 代码块标记
    for prefix in ("```python\n", "```python", "```\n", "```"):
        if fixed.startswith(prefix):
            fixed = fixed[len(prefix):]
    if fixed.endswith("\n```"):
        fixed = fixed[:-4]
    elif fixed.endswith("```"):
        fixed = fixed[:-3]
    return fixed.strip()


# ---------------------------------------------------------------------------
# MCP 工具
# ---------------------------------------------------------------------------


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


@mcp.custom_route("/dashboard", methods=["GET"])
async def dashboard(_: Request) -> PlainTextResponse:
    from starlette.responses import HTMLResponse
    return HTMLResponse(DASHBOARD_HTML)


@mcp.custom_route("/dashboard/api/executions", methods=["GET"])
async def dashboard_api(request: Request) -> PlainTextResponse:
    since = int(request.query_params.get("since", "0"))
    limit = min(int(request.query_params.get("limit", "100")), 500)
    return PlainTextResponse(
        json.dumps({
            "executions": get_executions(limit=limit, since_id=since),
            "stats": get_stats(),
        }, ensure_ascii=False),
        media_type="application/json",
    )


@mcp.tool
def list_installed_libraries() -> dict[str, Any]:
    """Report the fixed adapters available in this gateway image."""
    raw = os.environ.get("MCP_EXTRA_MODULES", "slugify")
    modules = [item.strip() for item in raw.split(",") if item.strip()]
    return {
        "fastmcp": "3.4.6",
        "modules": {module: bool(importlib.util.find_spec(module)) for module in modules},
        "allowlisted_tools": sorted(ALLOWED_TOOLS),
        "code_tool": "run_jwave_code",
        "auto_fix_tool": "run_jwave_code_with_retry",
        "deepseek_model": deepseek_model if deepseek_api_key else None,
    }


@mcp.tool
def run_allowlisted_tool(tool_name: str, arguments_json: str = "{}") -> Any:
    """Run one named adapter from the server's explicit allowlist."""
    if tool_name not in ALLOWED_TOOLS:
        raise ValueError(f"tool_name is not allowlisted: {tool_name}")
    try:
        arguments = json.loads(arguments_json)
    except json.JSONDecodeError as exc:
        raise ValueError("arguments_json must be valid JSON") from exc
    if not isinstance(arguments, dict):
        raise ValueError("arguments_json must encode a JSON object")
    return ALLOWED_TOOLS[tool_name](**arguments)


@mcp.tool
def jwave_environment() -> dict[str, Any]:
    """Report the packaged jwave environment and JAX device status."""
    response = httpx.get(
        "http://jwave-executor:8010/health",
        headers={"X-Executor-Token": executor_token},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


@mcp.tool
def run_jwave_code(code: str, timeout_seconds: int = 15) -> dict[str, Any]:
    """Run Dify-generated Python in the packaged jwave environment."""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be a non-empty Python string")
    code = _clean_code(code)
    if len(code) > 20000:
        raise ValueError("code is limited to 20000 characters")
    if not 1 <= timeout_seconds <= 30:
        raise ValueError("timeout_seconds must be between 1 and 30")
    result = _execute_code(code, timeout_seconds)
    record_execution(
        tool_name="run_jwave_code",
        code=code,
        exit_code=result.get("exit_code"),
        timed_out=result.get("timed_out", False),
        duration_ms=result.get("duration_ms"),
        stdout=result.get("stdout", ""),
        stderr=result.get("stderr", ""),
        attempt_count=1,
    )
    return result


@mcp.tool
def run_jwave_code_with_retry(
    code: str,
    timeout_seconds: int = 15,
    max_retries: int | None = None,
) -> dict[str, Any]:
    """Run Python code and auto-fix errors using DeepSeek LLM.

    Executes the code in the sandboxed jwave environment.  If the code fails
    (non-zero exit code or timeout), the tool sends the error output to DeepSeek
    and asks it to produce a corrected version, then re-executes.  This loop
    continues until the code succeeds or *max_retries* is exhausted.

    Returns a dict with ``final_code`` (the last version tried), ``history``
    (one entry per attempt), and the fields from the final execution.
    """
    if max_retries is None:
        max_retries = max_retries_default
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be a non-empty Python string")
    code = _clean_code(code)
    if len(code) > 20000:
        raise ValueError("code is limited to 20000 characters")
    if not 1 <= timeout_seconds <= 30:
        raise ValueError("timeout_seconds must be between 1 and 30")
    if not 0 <= max_retries <= 7:
        raise ValueError("max_retries must be between 0 and 7")

    if not deepseek_api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY must be set in the server environment "
            "to use auto-fix. Use run_jwave_code for plain execution."
        )

    current_code = code
    history: list[dict[str, Any]] = []

    for attempt in range(max_retries + 1):  # 首次 + N 次重试
        result = _execute_code(current_code, timeout_seconds)
        step = {
            "attempt": attempt + 1,
            "code": current_code,
            "exit_code": result["exit_code"],
            "timed_out": result["timed_out"],
            "duration_ms": result.get("duration_ms"),
            "stdout_tail": result.get("stdout", "")[-2000:],
            "stderr_tail": result.get("stderr", "")[-2000:],
        }
        history.append(step)

        # 成功 —— 直接返回
        if result["exit_code"] == 0 and not result["timed_out"]:
            result["history"] = history
            result["final_code"] = current_code
            result["total_attempts"] = attempt + 1
            record_execution(
                tool_name="run_jwave_code_with_retry",
                code=code,
                exit_code=result["exit_code"],
                timed_out=False,
                duration_ms=result.get("duration_ms"),
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                attempt_count=attempt + 1,
            )
            return result

        # 已达最大重试次数
        if attempt >= max_retries:
            result["history"] = history
            result["final_code"] = current_code
            result["total_attempts"] = attempt + 1
            result["error"] = "max_retries exhausted"
            record_execution(
                tool_name="run_jwave_code_with_retry",
                code=code,
                exit_code=result["exit_code"],
                timed_out=result.get("timed_out", False),
                duration_ms=result.get("duration_ms"),
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                attempt_count=attempt + 1,
            )
            return result

        # 调用 LLM 修正
        current_code = _llm_fix_code(
            deepseek_api_key,
            deepseek_model,
            current_code,
            result,
        )

    # 不应该走到这里，但保底
    return {"error": "unreachable", "history": history}


if __name__ == "__main__":
    init_db()
    mcp.run(transport="http", host="0.0.0.0", port=8001, path="/mcp", stateless_http=True)
