"""Web 门户路由：门户/看板/报告/缓存/Demo 页面与 API。

通过 `register(mcp)` 向网关注册 custom_route。
"""

import json
from pathlib import Path as _Path

import httpx
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse

import cache_store
import config
from dashboard import (
    CHAT_HTML,
    DEMO_HTML,
    PORTAL_HTML,
    clear_executions,
    get_executions,
    get_stats,
    load_test_results,
)


def _serve_html(filename: str) -> HTMLResponse:
    html = (_Path(__file__).parent / "docs" / filename).read_text(encoding="utf-8")
    return HTMLResponse(html)


def _extract_report(output) -> str:
    """从 Dify 工作流 outputs.text 中提取 Markdown 报告字符串。"""
    if isinstance(output, str):
        return output
    if isinstance(output, list) and output:
        first = output[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first.get("result", "") or first.get("report", "") or json.dumps(first, ensure_ascii=False)
    if isinstance(output, dict):
        return output.get("result", "") or output.get("report", "") or json.dumps(output, ensure_ascii=False)
    return ""


async def _merge_requirement(requirement: str, message: str) -> str:
    """用 DeepSeek 把「历史需求 + 本轮增量修改」合并成完整需求。"""
    if not config.DEEPSEEK_API_KEY:
        return f"{requirement}；{message}"
    prompt = (
        "你是声学仿真需求整理助手。请根据「当前完整需求」和「用户新修改」，输出更新后的完整需求。\n"
        "要求：输出一段完整的中文需求描述，包含所有当前有效的仿真参数"
        "（如声源频率、网格大小、仿真区域、声速、介质/异质结构、传感器位置、仿真时长等）；"
        "用户的新修改要覆盖旧值；只输出需求本身，不要任何解释或前缀。\n\n"
        f"当前完整需求：\n{requirement}\n\n"
        f"用户新修改：\n{message}\n\n"
        "更新后的完整需求："
    )
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.DEEPSEEK_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 1200,
                },
            )
        resp.raise_for_status()
        merged = resp.json()["choices"][0]["message"]["content"].strip()
        return merged or f"{requirement}；{message}"
    except Exception:
        return f"{requirement}；{message}"


def register(mcp) -> None:
    """向 FastMCP 实例注册本模块的全部 Web 路由。"""

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    @mcp.custom_route("/report", methods=["GET"])
    async def report_page(_: Request) -> PlainTextResponse:
        return _serve_html("report.html")

    @mcp.custom_route("/cache", methods=["GET"])
    async def cache_page(_: Request) -> PlainTextResponse:
        return _serve_html("cache.html")

    @mcp.custom_route("/ask", methods=["POST"])
    async def ask_api(request: Request) -> PlainTextResponse:
        """Proxy to Dify workflow API for portal-based queries."""
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
                    "Authorization": f"Bearer {config.DIFY_API_KEY}",
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

    @mcp.custom_route("/chat", methods=["POST"])
    async def chat_api(request: Request) -> PlainTextResponse:
        """多轮对话：合并历史需求 → 调用 Dify 工作流执行仿真。

        会话隔离：前端每次请求携带 session_id（浏览器 localStorage 持久化），
        Dify 侧 user 按会话区分（portal-<session>），避免多用户共享 Dify 会话上下文。
        """
        body = await request.json()
        message = (body.get("message") or "").strip()
        requirement = (body.get("requirement") or "").strip()
        session_id = (body.get("session_id") or "").strip()[:24]
        if not message:
            return PlainTextResponse(
                json.dumps({"error": "message is required"}, ensure_ascii=False),
                status_code=400, media_type="application/json",
            )

        if requirement:
            full_requirement = await _merge_requirement(requirement, message)
            merge_used = True
        else:
            full_requirement = message
            merge_used = False

        # 按会话隔离 Dify user（有 session 时用 portal-<session>，否则回退 portal）
        dify_user = f"portal-{session_id}" if session_id else "portal"

        dify_url = "http://nginx/v1/workflows/run"
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(
                    dify_url,
                    headers={
                        "Authorization": f"Bearer {config.DIFY_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "inputs": {"query": full_requirement},
                        "response_mode": "blocking",
                        "user": dify_user,
                    },
                )
            data = resp.json()
        except Exception as exc:
            return PlainTextResponse(
                json.dumps({
                    "report": f"_(调用 Dify 工作流失败：{exc})_",
                    "requirement": full_requirement,
                    "merge_used": merge_used,
                    "workflow_status": "error",
                }, ensure_ascii=False),
                media_type="application/json",
            )

        wf = data.get("data", {})
        report = _extract_report(wf.get("outputs", {}).get("text"))
        if not report or not report.strip():
            report = f"_(工作流返回空结果, status={wf.get('status')}, error={wf.get('error')})_"

        return PlainTextResponse(
            json.dumps({
                "report": report,
                "requirement": full_requirement,
                "merge_used": merge_used,
                "workflow_status": wf.get("status"),
            }, ensure_ascii=False),
            media_type="application/json",
        )

    @mcp.custom_route("/", methods=["GET"])
    async def portal(_: Request) -> PlainTextResponse:
        return HTMLResponse(PORTAL_HTML)

    @mcp.custom_route("/portal", methods=["GET"])
    async def portal_page(_: Request) -> PlainTextResponse:
        return HTMLResponse(PORTAL_HTML)

    @mcp.custom_route("/chat", methods=["GET"])
    async def chat_page(_: Request) -> PlainTextResponse:
        return HTMLResponse(CHAT_HTML)

    @mcp.custom_route("/dashboard", methods=["GET"])
    async def dashboard(_: Request) -> PlainTextResponse:
        return _serve_html("dashboard.html")

    @mcp.custom_route("/demo", methods=["GET"])
    async def demo_page(_: Request) -> PlainTextResponse:
        return HTMLResponse(DEMO_HTML)

    @mcp.custom_route("/demo/api/run", methods=["POST"])
    async def demo_api_run(request: Request) -> PlainTextResponse:
        """Proxy to Dify workflow API so browser-based demo can call Dify."""
        body = await request.json()
        dify_url = "http://nginx/v1/workflows/run"

        async with httpx.AsyncClient(timeout=130) as client:
            resp = await client.post(
                dify_url,
                headers={
                    "Authorization": f"Bearer {config.DIFY_API_KEY}",
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
            json.dumps(cache_store.get_cache_stats(), ensure_ascii=False),
            media_type="application/json",
        )
