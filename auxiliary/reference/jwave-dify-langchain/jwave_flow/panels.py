"""Rich 渲染件 —— CLI 的「可视化」全都由这里产出。

这里刻意只做**纯渲染**：输入是 workflow 的 state / Settings / 历史记录，
输出是可以直接交给 ``rich.console.Console.print`` 的对象，不读终端、不交互。
这样它既能在 Live 刷新里复用，也方便单元测试（record=True）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from rich import box
from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from .config import Settings

# --------------------------------------------------------------------------- #
# 状态与配色
# --------------------------------------------------------------------------- #
ICON = {
    "pending": "·",
    "running": "▶",
    "done": "✔",
    "warn": "▲",
    "fail": "✖",
    "retry": "↻",
}
STYLE = {
    "pending": "dim",
    "running": "bold yellow",
    "done": "green",
    "warn": "yellow",
    "fail": "bold red",
    "retry": "magenta",
}
BRAND = "bold cyan"
LOOP_STEPS = ("④ 参数提取", "④b 参数预检", "⑤ 代码生成", "⑤b 静态检查", "⑥ 执行", "⑥b 语义门", "⑦ 代码纠错")


@dataclass
class Step:
    """流水线里的一个节点（供 Live 面板渲染）。"""

    key: str
    label: str
    status: str = "pending"
    elapsed: float | None = None
    note: str = ""
    visits: int = 0

    def mark(self, status: str, *, elapsed: float | None = None, note: str = "") -> None:
        self.status = status
        if elapsed is not None:
            self.elapsed = elapsed
        if note:
            self.note = note
        if status in ("done", "warn", "fail"):
            self.visits += 1


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def clip(text: Any, limit: int) -> str:
    if text is None:
        return ""
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"…（已截断 {len(text) - limit} 字符）"


_clip = clip  # 内部沿用旧名


def _fmt_seconds(value: Any) -> str:
    try:
        secs = float(value or 0.0)
    except (TypeError, ValueError):
        return ""
    if secs <= 0:
        return ""
    if secs < 60:
        return f"{secs:.2f}s"
    return f"{int(secs // 60)}m{secs % 60:04.1f}s"


def bar(done: int, total: int, width: int = 28) -> Text:
    total = max(int(total), 1)
    done = max(0, min(int(done), total))
    filled = round(width * done / total)
    text = Text()
    text.append("█" * filled, style="green")
    text.append("─" * (width - filled), style="dim")
    text.append(f"  {done}/{total}", style="bold")
    return text


def badge(ok: bool, *, ok_text: str = "通过 ✅", bad_text: str = "未通过 ❌") -> Text:
    return Text(ok_text if ok else bad_text, style="green" if ok else "red")


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def try_parse_json(text: Any) -> Any | None:
    """从模型输出里尽力抠出 JSON（可能被 ``` 包裹）。"""
    if not isinstance(text, str):
        return None
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3]
    for candidate in (raw, raw[raw.find("{") : raw.rfind("}") + 1] if "{" in raw else ""):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
    return None


# --------------------------------------------------------------------------- #
# 页头 / 配置
# --------------------------------------------------------------------------- #
def banner(version: str, settings: Settings | None = None) -> Panel:
    title = Text()
    title.append("jwave 仿真工作流", style=f"{BRAND}")
    title.append("  ·  LangChain / LangGraph", style="dim")
    body = Text.from_markup(
        "[dim]自然语言需求 → 需求分析 → 知识检索 → 参数提取 → 代码生成 → 执行 → 纠错 → 语义校验[/]\n"
        f"[dim]三道关：[/][green]方案一 参数物理预检[/][dim] · [/][green]方案二 AST 静态检查[/][dim] · [/][green]方案三 语义数值门[/]"
    )
    group = Group(title, body)
    return Panel(group, box=box.ROUNDED, border_style="cyan", subtitle=f"v{version}", subtitle_align="right")


def config_table(settings: Settings, *, show_secret: bool = False) -> Table:
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold cyan", expand=False)
    table.add_column("配置项", style="bold")
    table.add_column("值")
    table.add_column("说明", style="dim")

    key = settings.openai_api_key or ""
    if key and not show_secret:
        key = key[:6] + "…" + key[-4:] if len(key) > 12 else "已设置"
    rows = [
        ("模型 (分析)", settings.analyst_model, "① 需求分析 / ④ 参数提取"),
        ("模型 (代码)", settings.coder_model, "⑤ 生成 / ⑦ 纠错"),
        ("API 端点", settings.openai_base_url or "OpenAI 官方", "OpenAI 兼容接口"),
        ("API Key", key or "未设置 ⚠️", "OPENAI_API_KEY"),
        ("知识库", str(settings.resolved_kb_path().name), "②③ 检索与模板转换"),
        ("检索", f"{settings.retrieval_backend} · top_k={settings.top_k}", "bm25 可离线"),
        ("执行后端", settings.executor_backend, f"超时 {settings.exec_timeout:g}s"),
        ("最大迭代", str(settings.max_iterations), "对应 Dify loop_count"),
        (
            "三道关",
            " ".join(
                [
                    "参数" + ("✅" if settings.param_check_enabled else "⛔"),
                    "静态" + ("✅" if settings.static_check_enabled else "⛔"),
                    "语义" + ("✅" if settings.semantic_check_enabled else "⛔"),
                ]
            ),
            "方案一 / 二 / 三",
        ),
    ]
    for label, value, note in rows:
        table.add_row(label, str(value), note)
    return table


def config_panel(settings: Settings, *, show_secret: bool = False) -> Panel:
    return Panel(
        config_table(settings, show_secret=show_secret),
        title="[bold]运行配置[/bold]",
        border_style="blue",
        box=box.ROUNDED,
    )


def task_panel(query: str, settings: Settings, *, extra: str = "") -> Panel:
    text = Text()
    text.append(_clip(query.strip(), 600) or "(空)", style="white")
    body: RenderableType = text
    if extra:
        body = Group(body, Text(extra, style="dim"))
    return Panel(
        body,
        title="[bold]本次任务[/bold]",
        border_style="cyan",
        box=box.ROUNDED,
        subtitle=f"{settings.retrieval_backend} · {settings.executor_backend}",
        subtitle_align="right",
    )


# --------------------------------------------------------------------------- #
# 流水线可视化
# --------------------------------------------------------------------------- #
def flow_line(steps: Sequence[Step]) -> Text:
    """把整条流水线压成一行（运行中时高亮当前节点）。"""
    text = Text(overflow="fold")
    for i, step in enumerate(steps):
        if i:
            text.append(" → ", style="dim")
        text.append(f"{ICON[step.status]} {step.label}", style=STYLE[step.status])
    return text


def pipeline_table(steps: Sequence[Step]) -> Table:
    table = Table(box=None, show_header=False, pad_edge=False, padding=(0, 1))
    table.add_column(width=1, justify="center")   # 树线
    table.add_column(width=2, justify="center")   # 图标
    table.add_column(style="bold")                # 节点名
    table.add_column(justify="right", width=8)    # 用时
    table.add_column(style="dim")                 # 备注
    for i, step in enumerate(steps):
        connector = "" if i == 0 else ("│" if step.status == "pending" else "┆")
        icon = Text(ICON[step.status], style=STYLE[step.status])
        label = Text(step.label, style=STYLE[step.status] if step.status != "pending" else "dim")
        if step.visits > 1:
            label.append(f"  ×{step.visits}", style="magenta")
        table.add_row(Text(connector, style="dim"), icon, label, Text(_fmt_seconds(step.elapsed), style="cyan"), Text(_clip(step.note, 90)))
    return table


def pipeline_panel(steps: Sequence[Step], *, title: str = "流程") -> Panel:
    done = sum(1 for s in steps if s.status in ("done", "warn"))
    body = Group(flow_line(steps), Text(), pipeline_table(steps), Text(), bar(done, len(steps)))
    return Panel(body, title=f"[bold]{title}[/bold]", border_style="cyan", box=box.ROUNDED)


def counters_panel(state: dict[str, Any], max_iterations: int) -> Panel:
    table = Table(box=None, show_header=False, pad_edge=False, padding=(0, 1))
    table.add_column(style="bold")
    table.add_column(justify="right")
    iterations = int(state.get("iterations") or 0)
    table.add_row("迭代轮次", Text(f"{iterations} / {max_iterations}", style="cyan"))
    table.add_row("④b 参数预检", Text(str(state.get("param_check_rounds") or 0), style="cyan"))
    table.add_row("⑤b 静态检查", Text(str(state.get("static_rounds") or 0), style="cyan"))
    if state.get("success") is not None:
        table.add_row("⑥ 执行", Text("通过 ✅" if state.get("success") else "报错 ❌"))
    if state.get("verified") is not None:
        table.add_row("⑥b 语义门", Text("通过 ✅" if state.get("verified") else "未通过 ❌"))
    if "param_check_ok" in state:
        table.add_row("④b 参数预检", Text("通过 ✅" if state.get("param_check_ok") else "未通过 ❌"))
    return Panel(table, title="[bold]关卡[/bold]", border_style="magenta", box=box.ROUNDED)


def log_panel(lines: Sequence[str], *, title: str = "最新动态", tail: int = 8) -> Panel:
    tail_lines = list(lines)[-tail:]
    body: RenderableType
    if tail_lines:
        body = Text("\n".join(f"· {line}" for line in tail_lines), style="white", overflow="fold")
    else:
        body = Text("等待第一个节点…", style="dim")
    return Panel(body, title=f"[bold]{title}[/bold]", border_style="blue", box=box.ROUNDED)


def live_view(
    query: str,
    settings: Settings,
    steps: Sequence[Step],
    state: dict[str, Any],
    trace: Sequence[str],
    *,
    elapsed: float,
    footer: str = "运行中…（Ctrl+C 可中断）",
) -> RenderableType:
    """Live 刷新的整屏内容。"""
    header = Panel(
        Group(
            Text(_clip(query.strip().replace("\n", " "), 100) or "(空)", style="bold white"),
            Text(
                f"模型 {settings.analyst_model}/{settings.coder_model} · 检索 {settings.retrieval_backend} "
                f"· 执行 {settings.executor_backend} · 已用 {_fmt_seconds(elapsed)}",
                style="dim",
            ),
        ),
        title="[bold]仿真任务[/bold]",
        border_style="cyan",
        box=box.ROUNDED,
    )
    return Group(header, pipeline_panel(steps), counters_panel(state, settings.max_iterations), log_panel(trace), Text(footer, style="dim"))


# --------------------------------------------------------------------------- #
# 各关卡 / 报告
# --------------------------------------------------------------------------- #
def issues_panel(title: str, issues: Iterable[str], *, style: str = "red", empty: str = "无") -> Panel:
    items = list(issues)
    if items:
        body: RenderableType = Text("\n".join(f"  • {i}" for i in items), style=style, overflow="fold")
    else:
        body = Text(f"  {empty}", style="dim")
    return Panel(body, title=f"[bold]{title}[/bold]", border_style=style, box=box.ROUNDED)


def params_panel(result: dict[str, Any], *, parsed: Any = None) -> Panel:
    params = parsed if parsed is not None else try_parse_json(result.get("params_json"))
    report = result.get("param_check_report") or {}
    scalars = report.get("scalars") if isinstance(report, dict) else None

    blocks: list[RenderableType] = []
    if isinstance(scalars, dict) and scalars:
        table = Table(box=box.SIMPLE_HEAD, header_style="bold cyan")
        table.add_column("规范参数")
        table.add_column("取值", justify="right")
        for key, value in scalars.items():
            table.add_row(str(key), str(value))
        blocks.append(table)
    elif isinstance(params, dict):
        body = json.dumps(params, ensure_ascii=False, indent=2)
        blocks.append(Syntax(body, "json", theme="ansi_dark", word_wrap=True))
    else:
        blocks.append(Text(_clip(result.get("params_json"), 1200) or "(未提取到参数)", style="dim"))

    report_lines: list[str] = []
    if isinstance(report, dict):
        for item in report.get("errors") or []:
            report_lines.append(f"[error] {item}")
        for item in report.get("warnings") or []:
            report_lines.append(f"[warn ] {item}")
        for item in report.get("constraints") or []:
            report_lines.append(f"[约束 ] {item}")
        for item in report.get("skipped") or []:
            report_lines.append(f"[跳过 ] {item}")
    if report_lines:
        blocks.append(Text())
        blocks.append(Text("\n".join(report_lines), style="yellow", overflow="fold"))

    return Panel(Group(*blocks), title="[bold]④/④b 参数提取与物理预检（方案一）[/bold]", border_style="yellow", box=box.ROUNDED)


def gates_table(result: dict[str, Any]) -> Table:
    table = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", expand=True)
    table.add_column("关卡", style="bold")
    table.add_column("结论")
    table.add_column("细节", style="dim")
    param_issues = _as_list(result.get("param_issues"))
    param_warnings = _as_list(result.get("param_warnings"))
    static_issues = _as_list(result.get("static_issues"))
    semantic_issues = _as_list(result.get("semantic_issues"))
    table.add_row(
        "方案一 参数物理预检",
        badge(bool(result.get("param_check_ok")), ok_text="通过 ✅", bad_text="未通过 ❌"),
        f"{len(param_warnings)} 条告警 · {len(param_issues)} 个错误",
    )
    table.add_row(
        "方案二 AST 静态检查",
        badge(not static_issues, ok_text="通过 ✅", bad_text=f"{len(static_issues)} 处问题 ❌"),
        f"第 {result.get('static_rounds') or 0} 轮",
    )
    table.add_row(
        "方案三 语义数值门",
        badge(bool(result.get("verified")), ok_text="通过 ✅", bad_text="未通过 ❌"),
        f"{len(semantic_issues)} 项 · 自检" + ("存在" if result.get("selfcheck") else "缺失"),
    )
    return table


def selfcheck_panel(result: dict[str, Any]) -> Panel:
    data = result.get("selfcheck") or {}
    table = Table(box=None, show_header=False, pad_edge=False, padding=(0, 1))
    table.add_column(style="bold")
    table.add_column()
    if isinstance(data, dict) and data:
        for key, value in data.items():
            table.add_row(str(key), str(value))
    else:
        table.add_row("自检行", Text("缺失（代码未遵守 __JWAVE_SELFCHECK__ 输出契约）", style="yellow"))
    return Panel(table, title="[bold]⑥b 自检数据[/bold]", border_style="green" if result.get("verified") else "yellow", box=box.ROUNDED)


def execution_panel(result: dict[str, Any]) -> Panel:
    blocks: list[RenderableType] = []
    ok = bool(result.get("success"))
    header = Text()
    header.append("运行成功 ✅" if ok else "运行失败 ❌", style="bold green" if ok else "bold red")
    header.append(f"   迭代 {result.get('iterations') or 0} 轮 · {_fmt_seconds(result.get('execution_time'))}", style="dim")
    blocks.append(header)
    stdout = _clip(result.get("stdout"), 2000)
    stderr = _clip(result.get("stderr"), 2000)
    if stdout:
        blocks.append(Text())
        blocks.append(Text("── stdout ──", style="dim"))
        blocks.append(Text(stdout, style="white", overflow="fold"))
    if stderr:
        blocks.append(Text())
        blocks.append(Text("── stderr ──", style="dim"))
        blocks.append(Text(stderr, style="red", overflow="fold"))
    files = _as_list(result.get("new_files"))
    if files:
        blocks.append(Text())
        blocks.append(Text("── 产物 ──", style="dim"))
        blocks.append(Text("\n".join(f"  📄 {f}" for f in files), style="cyan"))
    if len(blocks) == 1:
        blocks.append(Text("(无输出)", style="dim"))
    return Panel(Group(*blocks), title="[bold]⑥ 执行结果[/bold]", border_style="green" if ok else "red", box=box.ROUNDED)


def code_panel(code: str, *, title: str = "最终代码", max_lines: int = 400) -> Panel:
    text = code or ""
    lines = text.splitlines()
    truncated = len(lines) > max_lines
    shown = "\n".join(lines[:max_lines]) if truncated else text
    body: RenderableType = Syntax(shown or "# (空)", "python", theme="ansi_dark", line_numbers=True, word_wrap=True)
    subtitle = f"共 {len(lines)} 行" + (f"，仅显示前 {max_lines} 行（按 v 用分页器查看全文）" if truncated else "")
    return Panel(body, title=f"[bold]{title}[/bold]", border_style="green", box=box.ROUNDED, subtitle=subtitle, subtitle_align="right")


def _hints_block(hints: Sequence[str], summary: str) -> Group:
    head = Text(summary, style="bold red", overflow="fold")
    body: list[RenderableType] = [head, Text()]
    for hint in hints:
        style = "yellow" if hint.startswith("这是") else "white"
        body.append(Text(hint, style=style, overflow="fold"))
    return Group(*body)


def error_panel(title: str, exc: BaseException, *, settings: Any | None = None) -> Panel:
    """异常 -> 可直接打印的诊断面板（文案与 CLI 共用 errors 模块）。

    传入 ``settings`` 时会把「Key 与 endpoint 不匹配」这类配置问题排在网络建议之前。
    """
    from .errors import diagnose_error, error_summary

    return Panel(
        _hints_block(list(diagnose_error(exc, settings)), error_summary(exc)),
        title=f"[bold]{title}[/bold]",
        border_style="red",
        box=box.ROUNDED,
    )


def error_state_panel(state: dict[str, Any], *, title: str = "运行中断") -> Panel:
    """Runner 把失败写进 state（error / error_hints），这里负责渲染。"""
    hints = _as_list(state.get("error_hints"))
    summary = str(state.get("error") or "未知错误")
    if not hints:
        hints = ["可在「运行配置」里按 t 做一次 API 连通性测试，或直接用 --check-api 定位。"]
    return Panel(
        _hints_block(hints, summary),
        title=f"[bold]{title}[/bold]",
        border_style="red",
        box=box.ROUNDED,
    )


def requirement_panel(result: dict[str, Any]) -> Panel:
    text = _clip(result.get("requirement"), 2000) or "(无)"
    try:
        body: RenderableType = Markdown(text)
    except Exception:  # pragma: no cover - markdown 解析失败就退回纯文本
        body = Text(text)
    return Panel(body, title="[bold]① 需求分析[/bold]", border_style="blue", box=box.ROUNDED)


def kb_stats_panel(result: dict[str, Any]) -> Panel:
    docs = result.get("kb_docs") or []
    table = Table(box=None, show_header=False, pad_edge=False, padding=(0, 1))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("命中片段", str(len(docs)))
    table.add_row("模板上下文", f"{len(result.get('kb_context') or '')} 字符")
    bodies: list[RenderableType] = [table]
    for i, doc in enumerate(docs[:6], 1):
        page = getattr(doc, "page_content", None)
        meta = getattr(doc, "metadata", {}) or {}
        heading = meta.get("heading") or meta.get("source") or ""
        snippet = _clip((page or "").strip().replace("\n", " "), 220)
        bodies.append(Text(f"  {i}. {heading}\n     {snippet}", style="dim", overflow="fold"))
    return Panel(Group(*bodies), title="[bold]②③ 知识检索与模板转换[/bold]", border_style="blue", box=box.ROUNDED)


def result_header(result: dict[str, Any], elapsed: float | None = None) -> Panel:
    success = bool(result.get("success"))
    verified = bool(result.get("verified"))
    if success and verified:
        head, style = "任务完成：代码运行通过 + 语义校验通过", "bold green"
    elif success:
        head, style = "代码运行通过，但未通过语义校验", "bold yellow"
    else:
        head, style = "任务未跑通（已达最大迭代）", "bold red"
    text = Text()
    text.append(head, style=style)
    seconds = elapsed if elapsed is not None else result.get("elapsed")
    text.append(
        f"\n迭代 {result.get('iterations') or 0} 轮 · 耗时 {_fmt_seconds(seconds) or '?'}"
        f" · 执行 {result.get('executor_backend') or result.get('backend') or '-'}"
        f" · 产物 {len(_as_list(result.get('new_files')))} 个",
        style="dim",
    )
    return Panel(text, border_style=style.split()[-1], box=box.HEAVY)


def final_report(result: dict[str, Any], *, elapsed: float | None = None, code_title: str = "最终代码") -> RenderableType:
    """跑完之后的一屏总览。"""
    return Group(
        result_header(result, elapsed),
        Panel(gates_table(result), title="[bold]三道关结论[/bold]", border_style="magenta", box=box.ROUNDED),
        requirement_panel(result),
        kb_stats_panel(result),
        params_panel(result),
        issues_panel("方案二 静态检查问题", _as_list(result.get("static_issues")), empty="无问题 ✅"),
        selfcheck_panel(result),
        issues_panel("方案三 语义数值门问题", _as_list(result.get("semantic_issues")), empty="无问题 ✅"),
        execution_panel(result),
        code_panel(result.get("text") or result.get("code_final") or "", title=code_title),
    )


# --------------------------------------------------------------------------- #
# 知识库 / 历史
# --------------------------------------------------------------------------- #
def _is_section_title(name: str) -> bool:
    """知识库里 `# ✅ 正确: ...` 这类行是正文，不是章节；过滤掉。"""
    first = (name or "").strip()[:1]
    if not first:
        return False
    return first.isalnum() or "\u4e00" <= first <= "\u9fff"


def kb_outline(text: str) -> tuple[list[str], list[str], int]:
    """把 markdown 拆成 (顶层标题, 条目, 章节总数)。``# ✅ 正确: …`` 这类正文会被过滤。"""
    import re

    headings = re.findall(r"^(#{1,6})\s+(.*)$", text, re.MULTILINE)
    sections: list[str] = []
    entries: list[str] = []
    for hashes, raw in headings:
        name = raw.strip()
        if not _is_section_title(name):
            continue
        if len(hashes) <= 2:
            sections.append(name)
        else:
            entries.append(name)
    return sections, entries, len(sections) + len(entries)


def kb_overview_panel(kb_path: Path, *, limit: int = 32) -> Panel:
    if not kb_path.exists():
        return Panel(Text(f"知识库不存在：{kb_path}", style="red"), title="[bold]知识库[/bold]", border_style="red")

    text = kb_path.read_text(encoding="utf-8", errors="replace")
    sections, entries, total = kb_outline(text)

    table = Table(box=None, show_header=False, pad_edge=False, padding=(0, 1))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("路径", str(kb_path))
    table.add_row("字数", f"{len(text):,}")
    table.add_row("章节", f"{total} 个（{len(entries)} 个 API / 主题条目）")

    rows: list[RenderableType] = [table]
    for name in sections[:4]:
        rows.append(Text(f"◆ {name}", style="bold cyan"))
    rows.append(Text())
    for name in entries[:limit]:
        base, _, desc = name.partition("—")
        line = Text("  · ")
        line.append(base.strip() or name, style="white")
        if desc.strip():
            line.append(f"  — {desc.strip()}", style="dim")
        rows.append(line)
    if len(entries) > limit:
        rows.append(Text(f"  …另有 {len(entries) - limit} 个条目（用「搜索知识库」直接检索）", style="dim"))
    return Panel(Group(*rows), title=f"[bold]知识库 · {kb_path.name}[/bold]", border_style="blue", box=box.ROUNDED)


def history_table(records: Sequence[dict[str, Any]]) -> Table:
    from .history import status_icon

    table = Table(box=box.SIMPLE_HEAD, header_style="bold cyan", expand=True)
    table.add_column("#", justify="right", width=3)
    table.add_column("", width=2, justify="center")
    table.add_column("时间")
    table.add_column("需求")
    table.add_column("迭代", justify="right")
    table.add_column("耗时", justify="right")
    for i, rec in enumerate(records, 1):
        gates = rec.get("gates") or {}
        marks = "".join(
            [
                "参" if gates.get("param_ok") else "参✖",
                " ",
                "静" if gates.get("static_ok") else "静✖",
                " ",
                "语" if gates.get("semantic_ok") else "语✖",
            ]
        )
        table.add_row(
            str(i),
            status_icon(rec),
            str(rec.get("time") or "?"),
            _clip(rec.get("title") or rec.get("query") or "?", 44),
            str(rec.get("iterations") or 0),
            f"{float(rec.get('elapsed') or 0):.1f}s",
        )
    return table


def history_detail(record: dict[str, Any]) -> RenderableType:
    from .history import describe

    table = Table(box=None, show_header=False, pad_edge=False, padding=(0, 1))
    table.add_column(style="bold")
    table.add_column(overflow="fold")
    for label, value in describe(record):
        table.add_row(label, str(value))
    gates = record.get("gates") or {}
    blocks: list[RenderableType] = [Panel(table, title="[bold]历史详情[/bold]", border_style="blue", box=box.ROUNDED)]
    if record.get("error"):
        blocks.append(
            error_state_panel(
                {"error": record["error"], "error_hints": record.get("error_hints")},
                title="错误诊断",
            )
        )
    for title, key, style in (
        ("方案一 参数预检问题", "param_issues", "yellow"),
        ("方案一 参数告警", "param_warnings", "yellow"),
        ("方案二 静态检查问题", "static_issues", "red"),
        ("方案三 语义门问题", "semantic_issues", "red"),
    ):
        issues = _as_list(gates.get(key))
        if issues:
            blocks.append(issues_panel(title, issues, style=style))
    if record.get("stdout"):
        blocks.append(Panel(Text(_clip(record["stdout"], 1500), overflow="fold"), title="stdout", border_style="dim", box=box.ROUNDED))
    if record.get("code"):
        blocks.append(code_panel(record["code"], title="当时生成的代码"))
    return Group(*blocks)
