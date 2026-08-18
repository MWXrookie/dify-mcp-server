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

    @mcp.custom_route("/", methods=["GET"])
    async def portal(_: Request) -> PlainTextResponse:
        return HTMLResponse(PORTAL_HTML)

    @mcp.custom_route("/portal", methods=["GET"])
    async def portal_page(_: Request) -> PlainTextResponse:
        return HTMLResponse(PORTAL_HTML)

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
