"""FastMCP gateway with fixed tools and a guarded internal code executor."""

import base64
import importlib.util
import json
import os
from datetime import datetime, timezone
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
from dashboard import init_db, record_execution, clear_executions, PORTAL_HTML, DEMO_HTML, get_executions, get_stats, load_test_results


token = os.environ.get("MCP_AUTH_TOKEN")
executor_token = os.environ.get("EXECUTOR_SHARED_TOKEN")
deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY", "")
deepseek_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
max_retries_default = int(os.environ.get("CODE_RETRY_MAX", "7"))
dify_api_key = os.environ.get("DIFY_API_KEY", "")

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
    """去掉 LLM 输出中可能包裹的 markdown 代码块标记，并注入图片保存."""
    code = code.strip()
    for prefix in ("```python\n", "```python", "```\n", "```"):
        if code.startswith(prefix):
            code = code[len(prefix):]
    for suffix in ("\n```", "```"):
        if code.endswith(suffix):
            code = code[:-len(suffix)]
    code = code.strip()

    # ---- 防护 1: LLM 常用 .max() 而非 jnp.max(jnp.abs(...)) ----
    # JAX 的 .max() 在纯负值网格上返回 0。自动替换。
    import re
    code = re.sub(
        r'(?<![a-zA-Z_])'
        r'(\b[a-zA-Z_]\w*)\.max\(\s*\)',
        lambda m: (
            f'jnp.max(jnp.abs({m.group(1)}))'
            if m.group(1) not in ('jnp', 'jax', 'numpy', 'np')
            else m.group(0)
        ),
        code,
    )

    # ---- 防护 2: LLM 错误地用 .params[0] 取第一帧 ----
    # jwave simulate_wave_propagation 返回 shape=(Nt, Nx, Ny, 1)，
    # .params[0] 是 t=0 时刻（全零）。正确做法是对所有帧取 max。
    code = re.sub(
        r'\.params\s*\[\s*0\s*\]',
        '.params',
        code,
    )

    # ---- 防护 3: LLM 错误地用 .params[-1] 取最后一帧 ----
    # 最后一帧可能也不是最大值所在，改为取全部帧
    code = re.sub(
        r'\.params\s*\[\s*-\s*1\s*\]',
        '.params',
        code,
    )

    # ---- 注入图片保存代码 ----
    # 如果代码使用了 matplotlib 且没有调用 savefig，则自动注入
    has_matplotlib = bool(re.search(r'(import\s+matplotlib|from\s+matplotlib|plt\.)', code))
    has_savefig = bool(re.search(r'plt\.savefig|\.savefig\s*\(', code))
    has_figure = bool(re.search(r'plt\.figure|plt\.subplots|plt\.plot|plt\.imshow|plt\.pcolormesh|plt\.show', code))

    if has_matplotlib and has_figure and not has_savefig:
        code += (
            "\n\n# Auto-injected: save figure for gallery\n"
            "import os\n"
            "try:\n"
            "    plt.savefig('result.png', dpi=72, bbox_inches='tight')\n"
            "    print('__GALLERY_IMAGE_SAVED__')\n"
            "except Exception as __e:\n"
            "    print(f'__GALLERY_SAVE_FAILED__: {__e}', file=__import__('sys').stderr)\n"
        )

    return code


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


# ---------------------------------------------------------------------------
# 纠错经验缓存
# ---------------------------------------------------------------------------

import re
import sqlite3 as _sql
from pathlib import Path as _Path

from dashboard import DB_PATH

_CACHE_DB = _Path(DB_PATH).parent / "error_cache.db"


def _cache_db() -> _sql.Connection:
    """Get or create the error cache database."""
    db = _sql.connect(str(_CACHE_DB))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS error_fix_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            error_signature TEXT NOT NULL UNIQUE,
            fix_hint TEXT NOT NULL,
            hit_count INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            consecutive_fails INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.0,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    db.commit()
    return db


def _extract_error_signature(stderr: str, exit_code: int | None, stdout: str) -> str | None:
    """解析 stderr 提取错误签名： (错误类型, 对象名, 属性/问题)"""
    if not stderr and exit_code == 0 and stdout:
        # 检测全零输出
        if re.search(r'(?:最大压力|max.pressure|Max pressure).*[:=]\s*0[\.\s]', stdout):
            return "ZeroOutput|max_pressure|all_zeros"
        return None
    if not stderr:
        return None

    # 提取错误类型
    err_type = "UnknownError"
    m = re.search(r'(\w+Error|\w+Exception|\w+Warning)', stderr)
    if m:
        err_type = m.group(1)

    # 提取对象名
    obj_name = "unknown"
    m = re.search(r"'([^']+)' object has no attribute '(\w+)'", stderr)
    if m:
        obj_name = m.group(1).split(".")[-1]
        attr = m.group(2)
        return f"{err_type}|{obj_name}|{attr}"

    # has no attribute
    m = re.search(r"has no attribute '(\w+)'", stderr)
    if m:
        # Extract class name from "X object has no attribute"
        m2 = re.search(r"'([^']+)' object", stderr)
        obj = m2.group(1).split(".")[-1] if m2 else "object"
        return f"{err_type}|{obj}|{m.group(1)}"

    # broadcast_shapes
    if "broadcast_shapes" in stderr:
        return f"BroadcastError|broadcast_shapes|shape_mismatch"

    # positional/keyword argument errors
    m = re.search(r'(__init__\(\)|__call__\(\))\s+takes\s+(\d+)', stderr)
    if m:
        return f"TypeError|{m.group(1)}|arg_count"

    # signals must be / positions must be
    m = re.search(r'(signals must be|positions must be)', stderr)
    if m:
        return f"TypeError|Sources|{m.group(1)}"

    # np.save error (disk full)
    if "OSError" in stderr and "written" in stderr:
        return "OSError|np.save|disk_full"

    # Generic fallback
    key = stderr.split("\n")[-3] if len(stderr.split("\n")) > 2 else stderr[-100:]
    key = re.sub(r'File ".*?"', '', key).strip()[:80]
    return f"{err_type}|general|{key}" if key else None


def _query_cache(error_signature: str) -> dict | None:
    """查询缓存，返回置信度 >= 0.7 的条目."""
    if not error_signature:
        return None
    db = _cache_db()
    row = db.execute(
        "SELECT * FROM error_fix_cache WHERE error_signature = ? AND confidence >= 0.7",
        (error_signature,),
    ).fetchone()
    db.close()
    if row:
        return {"signature": row[1], "fix_hint": row[2], "confidence": row[6]}
    return None


def _update_cache(error_signature: str, fix_hint: str, was_successful: bool) -> None:
    """更新缓存：记录命中、成功/失败，管理质疑和退役."""
    if not error_signature or not fix_hint:
        return
    db = _cache_db()
    now = datetime.now(timezone.utc).isoformat()
    existing = db.execute(
        "SELECT * FROM error_fix_cache WHERE error_signature = ?",
        (error_signature,),
    ).fetchone()

    if existing:
        hit_count = existing[3] + 1
        if was_successful:
            success_count = existing[4] + 1
            consecutive_fails = 0
        else:
            success_count = existing[4]
            consecutive_fails = existing[5] + 1

        confidence = success_count / hit_count if hit_count > 0 else 0.0

        # 连续失败 >= 3: 标记质疑 (confidence 减半)
        if consecutive_fails >= 3:
            confidence = confidence * 0.5

        # 连续失败 >= 5: 删除
        if consecutive_fails >= 5:
            db.execute("DELETE FROM error_fix_cache WHERE error_signature = ?", (error_signature,))
            db.commit()
            db.close()
            return

        db.execute(
            """UPDATE error_fix_cache
               SET fix_hint = ?, hit_count = ?, success_count = ?,
                   consecutive_fails = ?, confidence = ?, updated_at = ?
               WHERE error_signature = ?""",
            (fix_hint, hit_count, success_count, consecutive_fails, confidence, now, error_signature),
        )
    else:
        confidence = 1.0 if was_successful else 0.0
        db.execute(
            """INSERT INTO error_fix_cache (error_signature, fix_hint, hit_count, success_count, consecutive_fails, confidence, created_at, updated_at)
               VALUES (?, ?, 1, ?, ?, ?, ?, ?)""",
            (error_signature, fix_hint, 1 if was_successful else 0, 0 if was_successful else 1, confidence, now, now),
        )
    db.commit()
    db.close()


def get_cache_stats() -> dict:
    """返回缓存统计数据."""
    db = _cache_db()
    rows = db.execute("SELECT * FROM error_fix_cache").fetchall()
    db.close()

    total = len(rows)
    total_hits = sum((row[3] or 0) for row in rows)
    total_success = sum((row[4] or 0) for row in rows)
    hit_rate = round(total_success / total_hits * 100, 1) if total_hits > 0 else 0.0
    confidences = [float(row[6] or 0.0) for row in rows if row[6] is not None]
    hits = [int(row[3] or 0) for row in rows]

    def _row_dict(row) -> dict:
        return {
            "signature": row[1],
            "hint": row[2],
            "hint_excerpt": (row[2] or "")[:160],
            "hits": row[3],
            "success_count": row[4],
            "consecutive_fails": row[5],
            "confidence": row[6],
            "created_at": row[7],
            "updated_at": row[8],
        }

    sorted_rows = sorted(rows, key=lambda row: ((row[3] or 0), (row[6] or 0.0)), reverse=True)
    recent_rows = sorted(rows, key=lambda row: row[8] or "", reverse=True)

    confidence_bands = {"0-50": 0, "50-70": 0, "70-90": 0, "90-100": 0}
    failure_streak_buckets = {"0": 0, "1-2": 0, "3-4": 0, "5+": 0}
    error_families: dict[str, int] = {}
    healthy_count = 0
    questioned_count = 0
    stale_count = 0

    for row in rows:
        confidence = float(row[6] or 0.0)
        streak = int(row[5] or 0)
        prefix = (row[1] or "general").split("|")[0]
        error_families[prefix] = error_families.get(prefix, 0) + 1

        if confidence < 0.5:
            confidence_bands["0-50"] += 1
        elif confidence < 0.7:
            confidence_bands["50-70"] += 1
        elif confidence < 0.9:
            confidence_bands["70-90"] += 1
        else:
            confidence_bands["90-100"] += 1

        if streak == 0:
            failure_streak_buckets["0"] += 1
        elif streak < 3:
            failure_streak_buckets["1-2"] += 1
        elif streak < 5:
            failure_streak_buckets["3-4"] += 1
        else:
            failure_streak_buckets["5+"] += 1

        if confidence >= 0.7 and streak < 3:
            healthy_count += 1
        elif streak >= 5:
            stale_count += 1
        elif streak >= 3:
            questioned_count += 1

    avg_hits_per_entry = round(total_hits / total, 2) if total > 0 else 0
    avg_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
    max_hits = max(hits) if hits else 0

    return {
        "total_entries": total,
        "total_hits": total_hits,
        "total_successes": total_success,
        "overall_hit_rate": hit_rate,
        "avg_hits_per_entry": avg_hits_per_entry,
        "avg_confidence": avg_confidence,
        "max_hits": max_hits,
        "healthy_count": healthy_count,
        "questioned_count": questioned_count,
        "stale_count": stale_count,
        "confidence_bands": confidence_bands,
        "failure_streak_buckets": failure_streak_buckets,
        "error_families": error_families,
        "top_entries": [_row_dict(row) for row in sorted_rows[:5]],
        "recent_entries": [_row_dict(row) for row in recent_rows[:5]],
    }


def _llm_fix_code(api_key: str, model: str, code: str, result: dict[str, Any]) -> str:
    """调用 DeepSeek API 修正出错的代码，返回修正后的代码字符串."""
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY must be set to use auto-fix")

    # ---- 提取错误签名，查缓存 ----
    stderr = result.get("stderr", "")
    stdout = result.get("stdout", "")
    exit_code = result.get("exit_code")
    error_sig = _extract_error_signature(stderr, exit_code, stdout)
    cache_hint = _query_cache(error_sig) if error_sig else None

    prompt = (
        "You are a Python debugging assistant. The following Python code was executed "
        "in a container with jwave, jax, jaxlib, jaxdf, equinox, and jaxtyping "
        "installed. JAX runs CPU-only. The code failed. Your job: return ONLY the "
        "corrected Python code. No markdown fences, no explanations — just raw, "
        "runnable Python.\n\n"
    )

    # ---- 注入缓存建议 ----
    if cache_hint:
        prompt += (
            "**KNOWN FIX EXPERIENCE** (confidence: {:.0f}%): {}"
            " If applicable, apply this fix directly.\n\n"
        ).format(cache_hint['confidence'] * 100, cache_hint['fix_hint'])
    else:
        prompt += (
            "**jwave common error cheat sheet (match by error message)**:\n"
            "- AttributeError: has no attribute 'shape' and object is FourierSeries → use .params.shape\n"
            "- AttributeError: has no attribute 'data' → use .params\n"
            "- AttributeError: has no attribute 't' → use .to_array()\n"
            "- AttributeError: 'FourierSeries' object has no attribute 'from_array' → use FourierSeries(data, domain)\n"
            "- TypeError: Sources.__init__() takes N positional arguments → use positional args, no keyword args\n"
            "- TypeError: signals must be array-like → signals must be 2D jnp array, shape=(num_sources, Nt)\n"
            "- TypeError: positions must be → positions must be tuple of 1D arrays\n"
            "- **CRITICAL - Sources returns all zeros**: positions must be INTEGERS (int32), NOT floats. "
            "Use jnp.array([64]) not jnp.array([64.0]). Float positions cause JAX .at[] index to fail silently in JIT, producing zero output.\n"
            "- **CRITICAL - pressure.params[0] is t=0 (all zeros)!**: simulate_wave_propagation returns a FourierSeries "
            "with shape (Nt, Nx, Ny, 1). params[0] extracts ONLY the first time step (t=0) where nothing has propagated yet. "
            "Correct: use jnp.max(jnp.abs(p.params)) for global max, or p.params[-1] for the final frame.\n"
            "- **CRITICAL - .max() returns 0 on negative grids**: don't use x.max() or pressure.max(). "
            "ALWAYS use jnp.max(jnp.abs(x)). This is a JAX behavior where .max() returns 0 when all values are negative.\n"
            "- **CRITICAL - p0/initial pressure returns all zeros**: if the user asked for \"initial pressure\", "
            "\"Gaussian pulse\", or \"p0\", the code should use simulate_wave_propagation(medium, time_axis, p0=p0) "
            "and NOT create Sources. Putting the Gaussian pressure into Sources() will produce zero output because Sources "
            "expects time-domain signals at point positions, not spatial pressure distributions. "
            "Fix: remove Sources entirely, create p0=FourierSeries(pressure_array, domain), then call "
            "simulate_wave_propagation with p0=p0 (no u0!). Use jnp.linspace + jnp.meshgrid to build the grid coordinates.\n"
            "- **CRITICAL - broadcast_shapes error**: the p0 field shape must match the domain grid (Nx, Ny). "
            "Construct p0 as a grid array of shape (Nx, Ny), then p0 = FourierSeries(grid_array, domain). "
            "Use jnp.meshgrid(x, y, indexing='ij') for correct array ordering.\n"
            "- **CRITICAL - signal shape mismatch / empty signal**: NEVER create jnp.zeros((0, Nt)) as a placeholder "
            "for no-source simulations. If no Sources are needed, simply omit the parameter: "
            "p = simulate_wave_propagation(medium, time_axis, p0=p0).\n\n"
        )

    prompt += (
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
    fixed = fixed.strip()

    return fixed


# ---------------------------------------------------------------------------
# MCP 工具
# ---------------------------------------------------------------------------


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


@mcp.custom_route("/report", methods=["GET"])
async def report_page(_: Request) -> PlainTextResponse:
    from pathlib import Path as _Path
    from starlette.responses import HTMLResponse
    html = (_Path(__file__).parent / "docs" / "report.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@mcp.custom_route("/cache", methods=["GET"])
async def cache_page(_: Request) -> PlainTextResponse:
    from pathlib import Path as _Path
    from starlette.responses import HTMLResponse
    html = (_Path(__file__).parent / "docs" / "cache.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@mcp.custom_route("/ask", methods=["POST"])
async def ask_api(request: Request) -> PlainTextResponse:
    """Proxy to Dify workflow API for portal-based queries."""
    import asyncio
    import re as _re
    body = await request.json()
    query = (body.get("query") or "").strip()
    if not query:
        return PlainTextResponse(
            json.dumps({"error": "query is required"}, ensure_ascii=False),
            status_code=400, media_type="application/json",
        )
    dify_url = "http://nginx/v1/workflows/run"
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            dify_url,
            headers={
                "Authorization": f"Bearer {dify_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "inputs": {"query": query},
                "response_mode": "blocking",
                "user": "portal",
            },
        )
    data = resp.json()
    wf = data.get("data", {})
    output = wf.get("outputs", {}).get("text")
    # Dify 返回的是 Markdown 字符串（代码节点 result 字段的值）
    report = ""
    if isinstance(output, str):
        report = output
    elif isinstance(output, list) and len(output) > 0:
        o = output[0]
        report = o if isinstance(o, str) else o.get("result", "") or o.get("report", "") or json.dumps(o, ensure_ascii=False)
    elif isinstance(output, dict):
        report = output.get("result", "") or output.get("report", "") or json.dumps(output, ensure_ascii=False)
    if not report or not report.strip():
        report = f"_(工作流返回空结果, status={wf.get('status')}, error={wf.get('error')})_"
    return PlainTextResponse(
        json.dumps({"report": report, "workflow_status": wf.get("status")}, ensure_ascii=False),
        media_type="application/json",
    )


@mcp.custom_route("/", methods=["GET"])
async def portal(_: Request) -> PlainTextResponse:
    from starlette.responses import HTMLResponse
    return HTMLResponse(PORTAL_HTML)


@mcp.custom_route("/portal", methods=["GET"])
async def portal_page(_: Request) -> PlainTextResponse:
    from starlette.responses import HTMLResponse
    return HTMLResponse(PORTAL_HTML)


@mcp.custom_route("/dashboard", methods=["GET"])
async def dashboard(_: Request) -> PlainTextResponse:
    from pathlib import Path as _Path
    from starlette.responses import HTMLResponse
    html = (_Path(__file__).parent / "docs" / "dashboard.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@mcp.custom_route("/demo", methods=["GET"])
async def demo_page(_: Request) -> PlainTextResponse:
    from starlette.responses import HTMLResponse
    return HTMLResponse(DEMO_HTML)


@mcp.custom_route("/demo/api/run", methods=["POST"])
async def demo_api_run(request: Request) -> PlainTextResponse:
    """Proxy to Dify workflow API so browser-based demo can call Dify."""
    import asyncio
    body = await request.json()
    dify_url = "http://nginx/v1/workflows/run"

    async with httpx.AsyncClient(timeout=130) as client:
        resp = await client.post(
            dify_url,
            headers={
                "Authorization": f"Bearer {dify_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )

    return PlainTextResponse(resp.text, media_type="application/json")


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


@mcp.custom_route("/dashboard/api/executions", methods=["DELETE"])
async def clear_executions_api(_: Request) -> PlainTextResponse:
    count = clear_executions()
    return PlainTextResponse(
        json.dumps({"deleted": count, "ok": True}, ensure_ascii=False),
        media_type="application/json",
    )


@mcp.custom_route("/dashboard/api/test_report", methods=["GET"])
async def test_report_api(_: Request) -> PlainTextResponse:
    return PlainTextResponse(
        json.dumps(load_test_results(), ensure_ascii=False),
        media_type="application/json",
    )


@mcp.custom_route("/dashboard/api/cache_stats", methods=["GET"])
async def cache_stats_api(_: Request) -> PlainTextResponse:
    return PlainTextResponse(
        json.dumps(get_cache_stats(), ensure_ascii=False),
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
        image_base64=result.get("image_base64"),
    )
    return result


def _build_report(result: dict[str, Any], original_code: str) -> str:
    """Build a human-readable Markdown report from execution results."""
    import re

    exit_code = result.get("exit_code")
    timed_out = result.get("timed_out", False)
    duration_ms = result.get("duration_ms")
    stdout = result.get("stdout", "") or ""
    stderr = result.get("stderr", "") or ""
    total_attempts = result.get("total_attempts", 1)
    image_base64 = result.get("image_base64")

    # Status
    if timed_out:
        status = "⏱ **超时** — 计算量超过资源限制"
    elif exit_code == 0:
        status = "✅ **成功** — 仿真正常完成"
    else:
        status = f"❌ **失败** — 退出码 {exit_code}"

    # Key metrics from stdout
    max_pressure = None
    pressure_shape = None
    m = re.search(r'(?:最大压力|max[_\s]pressure)\s*[:=]\s*([\d.eE+-]+)', stdout, re.I)
    if m:
        try:
            max_pressure = float(m.group(1))
        except ValueError:
            pass
    m = re.search(r'(?:压力场形状|pressure.*shape)\s*[:=]\s*\(?([\d,\s]+)\)?', stdout, re.I)
    if m:
        pressure_shape = m.group(1).strip().rstrip(")")

    lines = []
    lines.append("## 📊 仿真结果报告")
    lines.append("")
    lines.append("### ✅ 执行状态")
    lines.append("")
    lines.append(f"{status}")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("|------|-----|")
    lines.append(f"| 执行耗时 | {duration_ms:.0f} ms |" if duration_ms else "| 执行耗时 | - |")
    lines.append(f"| 尝试次数 | {total_attempts} 次 |")
    lines.append("")

    if max_pressure is not None or pressure_shape:
        lines.append("### 📈 关键数据")
        lines.append("")
        if max_pressure is not None:
            lines.append(f"- 最大压力：**{max_pressure:.4f}**")
        if pressure_shape:
            lines.append(f"- 压力场形状：`{pressure_shape}`")
        lines.append("")

    if stdout.strip():
        lines.append("### 📝 程序输出")
        lines.append("")
        lines.append("```")
        for line in stdout.strip().splitlines()[:30]:
            lines.append(line)
        if len(stdout.strip().splitlines()) > 30:
            lines.append(f"... (共 {len(stdout.strip().splitlines())} 行，省略后续)")
        lines.append("```")
        lines.append("")

    if stderr.strip():
        lines.append("### ⚠️ 错误输出")
        lines.append("")
        lines.append("```")
        for line in stderr.strip().splitlines()[:20]:
            lines.append(line)
        lines.append("```")
        lines.append("")

    if image_base64:
        lines.append("### 🖼 仿真图像")
        lines.append("")
        lines.append("*(图像已在看板中保存)*")
        lines.append("")

    return "\n".join(lines)


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
    last_error_sig: str | None = None

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
            result["report"] = _build_report(result, code)
            if last_error_sig:
                try:
                    _update_cache(last_error_sig, current_code[:500], was_successful=True)
                except Exception:
                    pass
            record_execution(
                tool_name="run_jwave_code_with_retry",
                code=code,
                exit_code=result["exit_code"],
                timed_out=False,
                duration_ms=result.get("duration_ms"),
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                attempt_count=attempt + 1,
                image_base64=result.get("image_base64"),
            )
            return result

        # 已达最大重试次数
        if attempt >= max_retries:
            result["history"] = history
            result["final_code"] = current_code
            result["total_attempts"] = attempt + 1
            result["error"] = "max_retries exhausted"
            result["report"] = _build_report(result, code)
            if last_error_sig:
                try:
                    _update_cache(last_error_sig, current_code[:500], was_successful=False)
                except Exception:
                    pass
            record_execution(
                tool_name="run_jwave_code_with_retry",
                code=code,
                exit_code=result["exit_code"],
                timed_out=result.get("timed_out", False),
                duration_ms=result.get("duration_ms"),
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                attempt_count=attempt + 1,
                image_base64=result.get("image_base64"),
            )
            return result

        # 调用 LLM 修正
        error_sig = _extract_error_signature(
            result.get("stderr", ""), result.get("exit_code"), result.get("stdout", "")
        )
        if error_sig:
            last_error_sig = error_sig
        current_code = _llm_fix_code(
            deepseek_api_key,
            deepseek_model,
            current_code,
            result,
        )

    # 不应该走到这里，但保底
    return {"error": "unreachable", "history": history}


@mcp.tool
def validate_simulation_params(params_json: str) -> dict[str, Any]:
    """Validate simulation parameters against physical rules before code generation.

    Checks Nyquist condition, CFL stability, grid size, PML layers,
    frequency-resolution matching, and time-propagation distance matching.
    All validation rules are hardcoded -- no LLM is called.
    """
    # Parse JSON input
    try:
        params = json.loads(params_json)
    except (json.JSONDecodeError, TypeError) as exc:
        return {
            "valid": False,
            "errors": [{"field": "_json", "message": f"JSON 解析失败: {exc}"}],
            "warnings": [],
        }

    if not isinstance(params, dict):
        return {
            "valid": False,
            "errors": [{"field": "_json", "message": "params_json 必须编码为一个 JSON 对象"}],
            "warnings": [],
        }

    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    # Extract fields
    sound_speed = params.get("sound_speed")
    density = params.get("density")
    source_frequency = params.get("source_frequency")
    domain_N = params.get("domain_N")
    domain_dx = params.get("domain_dx")
    t_end = params.get("t_end")
    cfl = params.get("cfl")
    pml_size = params.get("pml_size")

    # -------------------------------------------------------------------
    # 1. Required field check
    # -------------------------------------------------------------------
    required_fields = {
        "sound_speed": sound_speed,
        "density": density,
        "source_frequency": source_frequency,
        "domain_N": domain_N,
        "domain_dx": domain_dx,
    }
    required_field_names = set(required_fields.keys())

    for field_name, value in required_fields.items():
        if value is None:
            errors.append({"field": field_name, "message": f"缺少必填字段 {field_name}"})
        elif isinstance(value, list):
            if len(value) == 0:
                errors.append({"field": field_name, "message": f"{field_name} 为空列表"})
            else:
                for idx, elem in enumerate(value):
                    if not isinstance(elem, (int, float)) or elem <= 0:
                        errors.append({
                            "field": field_name,
                            "message": f"{field_name}[{idx}] = {elem} 必须 > 0",
                        })
        elif not isinstance(value, (int, float)) or value <= 0:
            errors.append({
                "field": field_name,
                "message": f"{field_name} 必须 > 0，当前值: {value}",
            })

    # If any required field is broken, stop -- downstream checks need them
    if any(e["field"] in required_field_names for e in errors):
        return {"valid": False, "errors": errors, "warnings": warnings}

    # Typecast for clarity -- at this point they are validated
    sound_speed = float(sound_speed)  # type: ignore[arg-type]
    source_frequency = float(source_frequency)  # type: ignore[arg-type]
    domain_N_list = domain_N if isinstance(domain_N, list) else [domain_N]  # type: ignore[union-attr]
    domain_dx_list = domain_dx if isinstance(domain_dx, list) else [domain_dx]  # type: ignore[union-attr]

    freq_mhz = source_frequency / 1e6

    # -------------------------------------------------------------------
    # 2. Nyquist condition
    # -------------------------------------------------------------------
    wavelength_min = sound_speed / source_frequency
    dx_max_allowed = wavelength_min / 4.0

    for i, dx in enumerate(domain_dx_list):
        dx = float(dx)
        if dx > dx_max_allowed * 1.001:  # floating-point tolerance
            errors.append({
                "field": "domain_dx",
                "message": (
                    f"dx({dx}m) 不满足 Nyquist 条件，"
                    f"{freq_mhz}MHz 对应的最小波长为 {wavelength_min:.6f}m，"
                    f"建议 dx ≤ {dx_max_allowed:.6f}m"
                ),
            })

    # -------------------------------------------------------------------
    # 3. CFL condition
    # -------------------------------------------------------------------
    if cfl is not None and isinstance(cfl, (int, float)):
        cfl = float(cfl)
        if cfl > 0.3 * 1.001:
            errors.append({
                "field": "cfl",
                "message": f"CFL({cfl}) 超过安全值 0.3，可能导致数值不稳定",
            })

    # -------------------------------------------------------------------
    # 4. Grid size
    # -------------------------------------------------------------------
    for i, n in enumerate(domain_N_list):
        n = int(n)
        if n < 32:
            errors.append({
                "field": "domain_N",
                "message": f"网格点数 {n} 过小（<32），jwave 0.2.1 可能存在 broadcasting 问题",
            })
        elif n > 1024:
            warnings.append({
                "field": "domain_N",
                "message": f"网格点数较大({n})，仿真可能耗时较长",
            })

    # -------------------------------------------------------------------
    # 5. PML check
    # -------------------------------------------------------------------
    if pml_size is not None and isinstance(pml_size, (int, float)):
        pml_size = int(pml_size)
        if pml_size < 10:
            warnings.append({
                "field": "pml_size",
                "message": f"PML 层数({pml_size})偏少，建议 ≥ 10 以保证吸收效果",
            })

    # -------------------------------------------------------------------
    # 6. Frequency-resolution matching (MHz ultrasound)
    # -------------------------------------------------------------------
    if source_frequency > 1e6:
        for i, dx in enumerate(domain_dx_list):
            dx = float(dx)
            if dx > 0.0005 * 1.001:
                errors.append({
                    "field": "domain_dx",
                    "message": (
                        f"对于 MHz 级超声({freq_mhz}MHz)，"
                        f"分辨率(dx={dx}m)过粗，建议 dx < 0.5mm"
                    ),
                })

    # -------------------------------------------------------------------
    # 7. Time-propagation distance matching
    # -------------------------------------------------------------------
    if t_end is not None and isinstance(t_end, (int, float)) and float(t_end) > 0:
        t_end_val = float(t_end)
        estimated_distance = sound_speed * t_end_val
        domain_length = max(
            float(domain_N_list[i]) * float(domain_dx_list[i])
            for i in range(min(len(domain_N_list), len(domain_dx_list)))
        )
        denom = min(estimated_distance, domain_length)
        if denom > 1e-20:
            ratio = max(estimated_distance, domain_length) / denom
            if ratio > 10:
                warnings.append({
                    "field": "t_end",
                    "message": (
                        f"仿真时间({t_end_val}s)对应传播距离约{estimated_distance:.4f}m，"
                        f"与区域大小({domain_length:.4f}m)偏差较大"
                    ),
                })

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


if __name__ == "__main__":
    init_db()
    mcp.run(transport="http", host="0.0.0.0", port=8001, path="/mcp", stateless_http=True)
