"""Command line entry point: ``python -m jwave_flow "你的需求"``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Settings
from .graph import SimulationWorkflow


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="jwave_flow",
        description='Dify 「仿真」工作流的 LangChain/LangGraph 实现',
    )
    p.add_argument("query", nargs="?", help="自然语言仿真需求")
    p.add_argument("--query-file", type=Path, help="从文件读取需求（与 query 二选一）")
    p.add_argument("--kb", type=Path, help="知识库 markdown 路径")
    p.add_argument("--top-k", type=int, help="知识检索命中数量（默认 4）")
    p.add_argument(
        "--retrieval", choices=["bm25", "openai"], help="检索后端（默认 bm25）"
    )
    p.add_argument(
        "--backend",
        choices=["subprocess", "jupyter", "mcp", "auto"],
        help="代码执行后端（默认 subprocess）",
    )
    p.add_argument("--max-iterations", type=int, help="执行/纠错最大轮数（默认 10）")
    p.add_argument("--model", help="同时覆盖 analyst/coder 模型名")
    p.add_argument("--out", type=Path, help="把最终代码写到该文件")
    p.add_argument("--json", action="store_true", help="以 JSON 打印完整最终状态")
    p.add_argument("--quiet", action="store_true", help="不打印过程日志")
    p.add_argument(
        "--check-api",
        action="store_true",
        help="只发一个最小请求验证 API/网络是否可达，然后退出",
    )
    p.add_argument("--tui", action="store_true", help="强制使用交互式界面（可视化流水线）")
    p.add_argument("--no-tui", action="store_true", help="禁用交互式界面（无需求时直接报错）")
    return p


def _overrides_from_args(args) -> dict:
    overrides: dict = {}
    if args.kb:
        overrides["kb_path"] = args.kb
    if args.top_k is not None:
        overrides["top_k"] = args.top_k
    if args.retrieval:
        overrides["retrieval_backend"] = args.retrieval
    if args.backend:
        overrides["executor_backend"] = args.backend
    if args.max_iterations is not None:
        overrides["max_iterations"] = args.max_iterations
    if args.model:
        overrides["analyst_model"] = args.model
        overrides["coder_model"] = args.model
    if args.quiet:
        overrides["verbose"] = False
    return overrides


def _check_api(overrides: dict) -> int:
    """``--check-api``：把「配置 / 网络 / 鉴权 / 模型名」问题单独暴露出来。

    先做**配置自洽性**检查（Key 与 endpoint 是否同一家），再发探测请求——
    否则会像以前那样：拿 DeepSeek 的 key 去探测 OpenAI 的地址，
    然后把「配置串了」误报成「网络不通」。
    """
    from .config import endpoint_key_mismatch, endpoint_provider, key_source
    from .errors import format_error_text
    from .llm import probe_api

    settings = Settings.from_env(**overrides)
    endpoint = settings.openai_base_url or "https://api.openai.com/v1"
    source = key_source()
    print(
        f"探测 {endpoint}（provider={endpoint_provider(settings.openai_base_url)}）\n"
        f"  模型: {settings.analyst_model}\n"
        f"  API Key: {'已配置' if settings.openai_api_key else '未配置 ⚠️'}"
        + (f"（来自 {source}）" if settings.openai_api_key and source else ""),
        file=sys.stderr,
    )
    if not settings.openai_api_key:
        print("❌ 未配置 API Key（OPENAI_API_KEY / DEEPSEEK_API_KEY）", file=sys.stderr)
        return 2

    mismatch = endpoint_key_mismatch(settings)
    if mismatch:
        print(f"❌ 配置不匹配，请先改这里（网络多半没问题）：\n  · {mismatch}", file=sys.stderr)
        return 2

    ok, payload, elapsed = probe_api(settings, timeout=20.0)
    if ok:
        print(f"✅ API 连通（{elapsed:.2f}s）\n  返回：{str(payload)[:200]}", file=sys.stderr)
        return 0
    print(
        f"❌ 连通性测试失败（{elapsed:.2f}s）\n  {format_error_text(payload, settings=settings)}",
        file=sys.stderr,
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    query = args.query
    if args.query_file:
        query = Path(args.query_file).read_text(encoding="utf-8").strip()

    if args.check_api:
        return _check_api(_overrides_from_args(args))

    # 没有需求时（或显式 --tui）进入交互式界面；有 --json 说明是脚本场景，不自动进 TUI
    wants_tui = args.tui or (
        not query and not args.no_tui and not args.json and sys.stdin is not None and sys.stdin.isatty()
    )
    if wants_tui:
        from .tui import RICH_AVAILABLE, run_tui

        if not RICH_AVAILABLE:
            print(
                "交互式界面需要 rich：pip install rich prompt_toolkit\n"
                "或改用非交互模式：jwave_flow \"你的需求\"",
                file=sys.stderr,
            )
            return 2
        return run_tui(
            _overrides_from_args(args),
            initial_query=(query or "").strip(),
            auto_out=args.out,
        )

    if not query:
        print("错误：请提供需求（位置参数 query 或 --query-file）", file=sys.stderr)
        return 2

    overrides = _overrides_from_args(args)
    settings = Settings.from_env(**overrides)
    print(f"知识库: {settings.resolved_kb_path()}", file=sys.stderr)
    print(
        f"模型: analyst={settings.analyst_model} coder={settings.coder_model} "
        f"base_url={settings.openai_base_url or '(openai default)'}",
        file=sys.stderr,
    )
    print(f"执行后端: {settings.executor_backend} | 检索: {settings.retrieval_backend}", file=sys.stderr)

    try:
        with SimulationWorkflow(settings) as wf:
            result = wf.invoke(query)
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return 130
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - 网络/服务端异常也要给人话，而不是 traceback
        from .errors import format_error_text

        print(f"\n运行失败：\n  {format_error_text(exc, settings=settings)}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({k: v for k, v in result.items() if k != "kb_docs"}, ensure_ascii=False, indent=2, default=str))
    else:
        print("\n" + "=" * 60)
        print("最终代码：\n")
        print(result.get("text", ""))
        print("=" * 60)
        print(
            f"迭代 {result.get('iterations')} 次 | 成功: {result.get('success')} | "
            f"耗时 {result.get('elapsed', 0):.1f}s",
            file=sys.stderr,
        )
        # 方案一/二/三：把三道关卡的结论一并交代清楚
        for line in result.get("param_warnings") or []:
            print(f"  {line}", file=sys.stderr)
        if result.get("param_issues"):
            print(
                f"  ❌ 参数预检未通过（{len(result['param_issues'])} 项）",
                file=sys.stderr,
            )
        if result.get("static_issues"):
            print(f"  ❌ 静态检查仍有 {len(result['static_issues'])} 处问题", file=sys.stderr)
        for line in result.get("semantic_issues") or []:
            print(f"  ❌ 语义门: {line}", file=sys.stderr)
        if result.get("verified"):
            print("  ✅ 语义校验通过", file=sys.stderr)
        else:
            print("  ⚠️ 未通过语义校验，请人工确认", file=sys.stderr)
            raw = (result.get("last_error") or result.get("stderr") or "").strip()
            if raw:
                print("  ---- 最近一次执行的错误输出 ----", file=sys.stderr)
                for line in raw.splitlines()[-15:]:
                    print(f"  | {line}", file=sys.stderr)

    if args.out:
        Path(args.out).write_text(result.get("text", ""), encoding="utf-8")
        print(f"已写入 {args.out}", file=sys.stderr)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
