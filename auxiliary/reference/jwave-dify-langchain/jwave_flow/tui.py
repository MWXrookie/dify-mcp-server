"""交互式 CLI（TUI）—— 让「仿真工作流」用起来更直观。

设计要点：

* **不改变后端**。所有执行都走 :class:`~jwave_flow.graph.SimulationWorkflow` 的
  ``stream()``，拿到的是各节点的 state 增量；UI 只做展示与编排。
* **分层**。渲染（``panels``）／历史（``history``）／交互（``tui``）互相独立，
  缺失 ``rich`` 或 ``prompt_toolkit`` 时能优雅降级。
* **可脚本化**。非交互场景仍然用 ``jwave_flow "需求"``（见 ``cli.py``）。
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from . import __version__
from . import errors
from .config import PROJECT_ROOT, Settings
from .history import (
    append_record,
    clear_records,
    history_path,
    load_records,
    make_record,
)

try:  # rich 是 TUI 的硬依赖，但只在真正进入 TUI 时才需要
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.text import Text

    from . import panels
    from .panels import Step

    RICH_AVAILABLE = True
except Exception:  # pragma: no cover - 依赖缺失时给出安装提示
    RICH_AVAILABLE = False

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.history import FileHistory

    PT_AVAILABLE = True
except Exception:  # pragma: no cover
    PT_AVAILABLE = False


class Abort(Exception):
    """用户主动取消当前流程。"""


# --------------------------------------------------------------------------- #
# 输入层
# --------------------------------------------------------------------------- #
class Prompter:
    """统一的输入层：优先 prompt_toolkit（行编辑 / 历史 / 补全），否则退回 input()。"""

    def __init__(self, console: "Console"):
        self.console = console
        self._session = None
        if PT_AVAILABLE and sys.stdin is not None and sys.stdin.isatty():
            history_file = PROJECT_ROOT / "run" / ".jwave_tui_history"
            try:
                history_file.parent.mkdir(parents=True, exist_ok=True)
                self._session = PromptSession(history=FileHistory(str(history_file)))
            except Exception:  # pragma: no cover
                self._session = None

    def ask(self, message: str = "› ", *, default: str | None = None, completions: Sequence[str] | None = None) -> str:
        kwargs: dict[str, Any] = {}
        if default:
            kwargs["default"] = default
        if completions:
            kwargs["completer"] = WordCompleter(list(completions), ignore_case=True, sentence=True)
        try:
            if self._session is not None:
                return self._session.prompt(message, **kwargs)
            return input(message)
        except (EOFError, KeyboardInterrupt):
            raise Abort() from None

    def confirm(self, message: str, *, default: bool = True) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        self.console.print(f"[bold cyan]?[/] {message} {suffix}")
        raw = self.ask("› ").strip().lower()
        if not raw:
            return default
        return raw in ("y", "yes", "是", "1")

    def choose(self, question: str, options: Sequence[tuple[str, str]], *, default: str | None = None) -> str:
        self.console.print(Text(question, style="bold"))
        for key, label in options:
            self.console.print(f"  [bold cyan]{key}[/]  {label}")
        allowed = [k for k, _ in options]
        while True:
            raw = self.ask("› ").strip().lower()
            if not raw and default:
                return default
            if raw in allowed:
                return raw
            self.console.print("[red]无效选择，请重新输入[/]")


# --------------------------------------------------------------------------- #
# .env 读写
# --------------------------------------------------------------------------- #
def upsert_env(path: Path, updates: dict[str, str], *, template: Path | None = None) -> Path:
    """就地更新 ``KEY=VALUE``，保留注释；缺失的键追加到文件末尾。"""
    if not path.exists():
        if template and template.exists():
            path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
    lines = path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    missing = [k for k in updates if k not in seen]
    if missing:
        out.extend(["", "# --- updated by jwave TUI ---"])
        out.extend(f"{k}={updates[k]}" for k in missing)
    path.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# 可编辑配置项
# --------------------------------------------------------------------------- #
@dataclass
class Field:
    key: str          # .env 里的变量名
    attr: str         # Settings 上的属性名
    label: str
    kind: str = "str"  # str | int | float | bool | choice
    choices: tuple[str, ...] = ()
    help: str = ""
    secret: bool = False


FIELDS: tuple[Field, ...] = (
    Field("OPENAI_API_KEY", "openai_api_key", "LLM API Key", secret=True, help="必填；也接受 DEEPSEEK_API_KEY"),
    Field("OPENAI_BASE_URL", "openai_base_url", "API 端点", help="OpenAI 兼容 base_url，留空=OpenAI 官方"),
    Field("ANALYST_MODEL", "analyst_model", "分析模型", help="① 需求分析 / ④ 参数提取"),
    Field("CODER_MODEL", "coder_model", "代码模型", help="⑤ 生成 / ⑦ 纠错"),
    Field("LLM_TEMPERATURE", "temperature", "温度", kind="float"),
    Field("LLM_TIMEOUT", "request_timeout", "请求超时(秒)", kind="float"),
    Field("KB_PATH", "kb_path", "知识库路径", help="相对路径按项目根解析"),
    Field("RETRIEVAL_BACKEND", "retrieval_backend", "检索后端", kind="choice", choices=("bm25", "openai")),
    Field("RETRIEVAL_TOP_K", "top_k", "检索 top_k", kind="int"),
    Field("EXECUTOR_BACKEND", "executor_backend", "执行后端", kind="choice", choices=("subprocess", "jupyter", "mcp", "auto")),
    Field("EXEC_PYTHON", "exec_python", "执行解释器", help="跑生成代码用的 python，留空=当前解释器"),
    Field("EXEC_TIMEOUT", "exec_timeout", "执行超时(秒)", kind="float"),
    Field("LOOP_MAX_ITERATIONS", "max_iterations", "最大迭代轮数", kind="int", help="对应 Dify loop_count"),
    Field("PARAM_CHECK", "param_check_enabled", "方案一 参数物理预检", kind="bool"),
    Field("MIN_POINTS_PER_WAVELENGTH", "min_points_per_wavelength", "每波长最少网格点", kind="float"),
    Field("STATIC_CHECK", "static_check_enabled", "方案二 AST 静态检查", kind="bool"),
    Field("SEMANTIC_CHECK", "semantic_check_enabled", "方案三 语义数值门", kind="bool"),
    Field("REQUIRE_SELFCHECK", "require_selfcheck", "强制 __JWAVE_SELFCHECK__", kind="bool"),
    Field("MAX_ABS_MAX", "max_abs_max", "|p|max 上限", kind="float", help="超过即视为发散"),
    Field("VERBOSE", "verbose", "流水线日志", kind="bool", help="TUI 下建议关闭"),
)


def _render_field_value(field: Field, value: Any, *, show_secret: bool = False) -> str:
    if field.kind == "bool":
        return "✅ 开" if value else "⛔ 关"
    if value in (None, ""):
        return "(未设置)"
    text = str(value)
    if field.secret and not show_secret:
        return text[:6] + "…" + text[-4:] if len(text) > 12 else "已设置"
    return text


# --------------------------------------------------------------------------- #
# 流水线执行器
# --------------------------------------------------------------------------- #
STEP_DEFS: tuple[tuple[str, str], ...] = (
    ("analyze", "① 需求分析"),
    ("retrieve", "② 知识检索"),
    ("template", "③ 模板转换"),
    ("extract", "④ 参数提取"),
    ("param_check", "④b 参数物理预检"),
    ("generate", "⑤ 代码生成"),
    ("static_check", "⑤b 静态检查"),
    ("run_code", "⑥ 执行"),
    ("semantic_gate", "⑥b 语义数值门"),
    ("fix_code", "⑦ 代码纠错"),
    ("finalize", "⑧ 输出"),
)
STEP_INDEX = {key: i for i, (key, _) in enumerate(STEP_DEFS)}


def next_node(node: str, state: dict[str, Any], max_iterations: int) -> str | None:
    """静态复刻 ``graph.py`` 的路由，用来在 UI 上提前高亮「下一个要跑的节点」。

    只用于显示；真正的路由始终由 LangGraph 决定。
    """
    if node == "analyze":
        return "retrieve"
    if node == "retrieve":
        return "template"
    if node == "template":
        return "extract"
    if node == "extract":
        return "param_check"
    if node == "param_check":
        if state.get("param_check_ok"):
            return "generate"
        if int(state.get("param_check_rounds") or 0) >= max_iterations:
            return "generate"
        return "extract"
    if node == "generate":
        return "static_check"
    if node == "static_check":
        if not state.get("static_issues"):
            return "run_code"
        if int(state.get("static_rounds") or 0) >= max_iterations:
            return "run_code"
        return "fix_code"
    if node == "run_code":
        if state.get("success"):
            return "semantic_gate"
        if int(state.get("iterations") or 0) >= max_iterations:
            return "semantic_gate"
        return "fix_code"
    if node == "semantic_gate":
        if state.get("verified"):
            return "finalize"
        if int(state.get("iterations") or 0) >= max_iterations:
            return "finalize"
        return "fix_code"
    if node == "fix_code":
        return "static_check"
    return None


def running_step_index(steps: Sequence[Step]) -> int | None:
    """最近被标记为 running 的节点（用于把异常归到具体节点上）。"""
    for i in range(len(steps) - 1, -1, -1):
        if steps[i].status == "running":
            return i
    return None


def step_outcome(node: str, state: dict[str, Any]) -> tuple[str, str]:
    """(状态, 备注) —— 根据 state 增量决定节点是成功还是失败。"""
    if node == "analyze":
        return "done", panels.clip(str(state.get("requirement") or "").strip().replace("\n", " "), 70)
    if node == "retrieve":
        return "done", f"命中 {len(state.get('kb_docs') or [])} 个片段"
    if node == "template":
        return "done", f"{len(state.get('kb_context') or '')} 字符上下文"
    if node == "extract":
        return "done", panels.clip(str(state.get("params_json") or "").replace("\n", " "), 70)
    if node == "param_check":
        warnings = len(state.get("param_warnings") or [])
        if state.get("param_check_ok"):
            return "done", f"通过（{warnings} 条告警）"
        return "fail", f"{len(state.get('param_issues') or [])} 个错误，第 {state.get('param_check_rounds')} 轮"
    if node == "generate":
        return "done", f"{len(state.get('code') or '')} 字符"
    if node == "static_check":
        issues = len(state.get("static_issues") or [])
        if issues:
            return "fail", f"{issues} 处问题，第 {state.get('static_rounds')} 轮"
        return "done", "无问题"
    if node == "run_code":
        backend = state.get("backend") or ""
        secs = float(state.get("execution_time") or 0.0)
        if state.get("success"):
            return "done", f"通过（{backend} {secs:.2f}s）"
        return "fail", f"报错（第 {state.get('iterations')} 次运行）"
    if node == "semantic_gate":
        if state.get("verified"):
            data = state.get("selfcheck") or {}
            abs_max = data.get("abs_max") if isinstance(data, dict) else None
            extra = f" |p|max={abs_max:g}" if isinstance(abs_max, (int, float)) else ""
            return "done", f"通过{extra}"
        return "fail", f"{len(state.get('semantic_issues') or [])} 项未通过"
    if node == "fix_code":
        return "retry", f"{len(state.get('code_final') or '')} 字符"
    if node == "finalize":
        return "done", "已输出最终代码"
    return "done", ""


class Runner:
    """把 workflow 的 stream 事件翻译成 Live 界面。"""

    def __init__(
        self,
        settings: Settings,
        console: "Console",
        *,
        workflow_factory: Callable[[Settings], Any] | None = None,
    ):
        self.settings = settings
        self.console = console
        self._factory = workflow_factory
        self._cancel = threading.Event()

    # -- 内部 ---------------------------------------------------------- #
    def _make_workflow(self):
        if self._factory is not None:
            return self._factory(self.settings)
        from .graph import SimulationWorkflow

        return SimulationWorkflow(self.settings)

    def _render(
        self,
        query: str,
        steps: list[Step],
        state: dict[str, Any],
        trace: list[str],
        elapsed: float,
        footer: str = "运行中…（Ctrl+C 可中断）",
    ):
        return panels.live_view(
            query, self.settings, steps, state, trace, elapsed=elapsed, footer=footer
        )

    # -- 对外 ---------------------------------------------------------- #
    def run(self, query: str) -> tuple[dict[str, Any], float]:
        """执行一次任务，返回 (最终 state, 耗时秒)。"""
        settings = self.settings
        # TUI 自己画进度，关掉节点里的 stderr 打印（否则会撕裂 Live 界面）
        settings.verbose = False
        wf = self._make_workflow()

        steps = [Step(key=key, label=label) for key, label in STEP_DEFS]
        state: dict[str, Any] = {"iterations": 0, "param_check_rounds": 0, "static_rounds": 0}
        trace: list[str] = []
        events: "queue.Queue[tuple[str, Any]]" = queue.Queue()
        started = time.time()

        def worker() -> None:
            try:
                with wf:
                    for chunk in wf.stream(query):
                        if self._cancel.is_set():
                            break
                        events.put(("update", chunk))
                events.put(("done", None))
            except BaseException as exc:  # noqa: BLE001 - 原样抛回主线程
                events.put(("error", exc))

        thread = threading.Thread(target=worker, name="jwave-workflow", daemon=True)
        thread.start()

        steps[0].mark("running")
        last_event = time.time()
        interrupted = False
        failure: BaseException | None = None

        live = Live(
            self._render(query, steps, state, trace, 0.0),
            console=self.console,
            refresh_per_second=12,
            transient=False,
            vertical_overflow="visible",
        )
        try:
            with live:
                while True:
                    try:
                        kind, payload = events.get(timeout=0.1)
                    except queue.Empty:
                        live.update(self._render(query, steps, state, trace, time.time() - started))
                        continue

                    now = time.time()
                    delta = now - last_event
                    last_event = now

                    if kind == "update":
                        for node, update in (payload or {}).items():
                            if node not in STEP_INDEX or not isinstance(update, dict):
                                continue
                            state.update(update)
                            if isinstance(update.get("trace"), list):
                                trace = list(update["trace"])
                            status, note = step_outcome(node, state)
                            steps[STEP_INDEX[node]].mark(status, elapsed=delta, note=note)
                            # 提前高亮「下一个要跑的节点」（纯展示，真正路由由 LangGraph 决定）
                            nxt = next_node(node, state, settings.max_iterations)
                            if nxt:
                                steps[STEP_INDEX[nxt]].mark("running")
                        live.update(self._render(query, steps, state, trace, time.time() - started))
                    elif kind == "error":
                        failure = payload
                        # 把失败落到具体节点上，让最后一帧仍然可读
                        idx = running_step_index(steps)
                        if idx is not None:
                            steps[idx].mark("fail", note=errors.error_summary(payload))
                        live.update(self._render(
                            query, steps, state, trace, time.time() - started,
                            footer="✖ 节点执行失败，已停止本次流程（诊断见下方面板）",
                        ))
                        break
                    else:
                        break
        except KeyboardInterrupt:
            interrupted = True
            self._cancel.set()
            self.console.print("[yellow]已中断；当前节点结束后会停止后续流程。[/]")
        finally:
            thread.join(timeout=2.0)

        elapsed = time.time() - started
        state["elapsed"] = elapsed
        if failure is not None:
            # 不抛出：交给调用方决定怎么展示（TUI 弹面板 / CLI 打日志）
            state["error"] = errors.error_summary(failure)
            state["error_type"] = type(failure).__name__
            state["error_hints"] = errors.diagnose_error(failure, self.settings)
            state["success"] = False
            state["verified"] = False
        elif interrupted:
            state.setdefault("success", False)
            state.setdefault("verified", False)
        return state, elapsed


# --------------------------------------------------------------------------- #
# 主应用
# --------------------------------------------------------------------------- #
PRESETS: tuple[tuple[str, str], ...] = (
    ("二维时域声学仿真", "生成一个 128x128 的二维时域声学仿真，声速 1500 m/s，5 MHz 点源"),
    ("三维小域声学", "生成一个 64x64x64 的三维时域声学仿真，声速 1500 m/s，1 MHz 点源，仿真 30 微秒"),
    ("带点源与探针", "二维时域声学仿真：128x128 网格，声速 1500 m/s，5 MHz 点源在 (32,32)，并在 (96,96) 放接收器"),
    ("线性声学验证", "用 jwave 做二维均匀介质中的线性声传播验证，声速 1500 m/s，频率 2.5 MHz，输出压力场最大值"),
)

COMMANDS = [
    ":help", ":settings", ":kb", ":history", ":run", ":quit",
    "预设", "示例",
]


class TuiApp:
    def __init__(
        self,
        settings: Settings,
        *,
        overrides: dict[str, Any] | None = None,
        console: "Console | None" = None,
        initial_query: str = "",
        auto_out: Path | None = None,
        workflow_factory: Callable[[Settings], Any] | None = None,
    ):
        self.console = console or Console()
        self.initial_query = initial_query
        self.auto_out = auto_out
        self._factory = workflow_factory
        self.overrides = dict(overrides or {})
        self.settings = settings
        self.prompter = Prompter(self.console)
        self.hist_file = history_path()
        self.last_result: dict[str, Any] | None = None
        self.last_query: str = ""
        self.last_elapsed: float = 0.0

    # -- 基础 ------------------------------------------------------------ #
    def reload_settings(self) -> None:
        self.settings = Settings.from_env(**self.overrides)

    # -- 菜单 ------------------------------------------------------------ #
    def main_menu(self) -> str:
        self.console.print()
        self.console.print(panels.banner(__version__))
        stats = f"知识库：{self.settings.resolved_kb_path().name}　模型：{self.settings.analyst_model}"
        if self.settings.openai_api_key:
            stats += "　[green]API Key 已配置[/]"
        else:
            stats += "　[red]API Key 未配置（先按 2）[/]"
        self.console.print(f"[dim]{stats}[/dim]")
        return self.prompter.choose(
            "请选择操作：",
            [
                ("1", "新建仿真任务（自然语言 → 代码 → 执行 → 校验）"),
                ("2", "运行配置（模型 / 后端 / 三道关）"),
                ("3", "知识库速览"),
                ("4", "历史记录"),
                ("5", "使用说明"),
                ("q", "退出"),
            ],
            default="1",
        )

    def run(self) -> int:
        self.console.print(
            f"[dim]jwave 仿真工作流 CLI v{__version__} · 输入 [/][bold]:help[/][dim] 查看命令，[/][bold]q[/][dim] 退出[/dim]"
        )
        if self.initial_query:
            pending, self.initial_query = self.initial_query, ""
            self.new_task(prefill=pending)
        while True:
            try:
                choice = self.main_menu()
            except Abort:
                break
            try:
                if choice == "1":
                    self.new_task()
                elif choice == "2":
                    self.edit_settings()
                elif choice == "3":
                    self.show_kb()
                elif choice == "4":
                    self.show_history()
                elif choice == "5":
                    self.show_help()
                else:
                    break
            except Abort:
                self.console.print("[dim]已取消[/dim]")
            except Exception as exc:  # noqa: BLE001 - 界面兜底：不把 traceback 甩给用户
                self.console.print(panels.error_panel("操作失败", exc, settings=self.settings))
                if os.environ.get("JWAVE_DEBUG"):
                    raise
        self.console.print("[dim]再见 👋[/dim]")
        return 0

    # -- 新建任务 -------------------------------------------------------- #
    def ask_requirement(self) -> str:
        self.console.print()
        self.console.print(Panel(
            Text.from_markup(
                "用一句话描述你要的仿真；也可以整段粘贴（含换行）。\n"
                "[dim]命令：[/][bold]:help[/][dim] 帮助 · [/][bold]:settings[/][dim] 改配置 · "
                "[/][bold]:kb[/bold] 知识库 · [bold]:history[/bold] 历史 · [bold]@file.txt[/bold] 从文件读 · "
                "[bold]:preset[/bold] 用示例 · [bold]:q[/bold] 取消"
            ),
            title="[bold]输入需求[/bold]",
            border_style="cyan",
            box=panels.box.ROUNDED,
        ))
        raw = self.prompter.ask("› ", completions=COMMANDS)
        return self._resolve_command(raw) or ""

    def _resolve_command(self, raw: str) -> str | None:
        text = (raw or "").strip()
        low = text.lower()
        if low in (":q", ":quit", ":cancel"):
            raise Abort()
        if low in (":help", ":h"):
            self.show_help()
            return self.ask_requirement()
        if low in (":settings", ":s", ":config"):
            self.edit_settings()
            return self.ask_requirement()
        if low in (":kb", ":k"):
            self.show_kb()
            return self.ask_requirement()
        if low in (":history", ":hist"):
            self.show_history()
            return self.ask_requirement()
        if low in (":preset", ":presets", ":example", ":run"):
            text = self.pick_preset()
        elif text.startswith("@"):
            path = Path(text[1:].strip() or self.prompter.ask("文件路径 › ")).expanduser()
            try:
                body = path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                self.console.print(f"[red]读取失败：{exc}[/red]")
                return self.ask_requirement()
            self.console.print(f"[green]已从 {path} 读取 {len(body)} 字符[/green]")
            text = body
        if not text:
            self.console.print("[red]需求不能为空[/red]")
            return self.ask_requirement()
        return text

    def pick_preset(self) -> str:
        self.console.print("[bold]选择一个示例需求：[/bold]")
        for i, (name, _) in enumerate(PRESETS, 1):
            self.console.print(f"  [bold cyan]{i}[/]  {name}")
        raw = self.prompter.ask("› ").strip()
        try:
            idx = int(raw) - 1
            _, query = PRESETS[idx]
        except (ValueError, IndexError):
            self.console.print("[red]无效选择[/red]")
            return self.ask_requirement()
        self.console.print(f"[dim]已选：{query}[/dim]")
        return query

    def new_task(self, prefill: str = "") -> None:
        query = (prefill or "").strip() or self.ask_requirement()
        if not query:
            return
        self.console.print()
        self.console.print(panels.task_panel(query, self.settings))
        self.console.print(panels.config_panel(self.settings))
        if not self.settings.openai_api_key:
            self.console.print(Panel(
                Text("未检测到 OPENAI_API_KEY / DEEPSEEK_API_KEY。\n请先运行 `jwave_flow --tui` 里的「运行配置」写入 .env，或直接编辑 .env。", style="red"),
                title="[bold]缺少 API Key[/bold]", border_style="red", box=panels.box.ROUNDED,
            ))
            if self.prompter.confirm("现在打开配置编辑器？", default=True):
                self.edit_settings()
            return
        if not self.prompter.confirm("开始运行？", default=True):
            return

        runner = Runner(self.settings, self.console, workflow_factory=self._factory)
        try:
            result, elapsed = runner.run(query)
        except Abort:
            return
        except KeyboardInterrupt:
            self.console.print("[yellow]已中断[/yellow]")
            return
        except Exception as exc:  # noqa: BLE001 - 兜底：再意外也不能把 traceback 甩给用户
            self.console.print(panels.error_panel("运行失败", exc, settings=self.settings))
            return

        # 节点里抛出的异常被 Runner 记进 state（而不是一路抛上来）
        if result.get("error"):
            self.last_result, self.last_query, self.last_elapsed = result, query, elapsed
            self.console.print(panels.error_state_panel(result, title="运行中断：节点执行失败"))
            self.console.print("[dim]提示：在「运行配置」里按 t 可以直接测一次 API 连通性。[/dim]")
            self._save_history(result, query, elapsed)
            return

        self.last_result, self.last_query, self.last_elapsed = result, query, elapsed
        self.console.print(panels.final_report(result, elapsed=elapsed))
        self._save_history(result, query, elapsed)
        if self.auto_out:
            self._write_code(self.auto_out)
        self._post_run_menu()

    def _write_code(self, path: Path) -> None:
        code = (self.last_result or {}).get("text") or ""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(code, encoding="utf-8")
        except OSError as exc:
            self.console.print(f"[red]写入 {path} 失败：{exc}[/red]")
            return
        self.console.print(f"[green]已写入 {path}[/green]")

    def _save_history(self, result: dict[str, Any], query: str, elapsed: float) -> None:
        try:
            record = make_record(result, query, self.settings, elapsed=elapsed)
            path = append_record(record, self.hist_file)
            self.console.print(f"[dim]已写入历史：{path}[/dim]")
        except OSError as exc:
            self.console.print(f"[yellow]历史写入失败：{exc}[/yellow]")

    def _post_run_menu(self) -> None:
        while True:
            choice = self.prompter.choose(
                "接下来：",
                [
                    ("s", "保存最终代码到文件"),
                    ("v", "用分页器查看完整代码"),
                    ("j", "查看完整 JSON 状态"),
                    ("r", "用同一需求重跑"),
                    ("m", "返回主菜单"),
                ],
                default="m",
            )
            if choice == "s":
                self._save_code()
            elif choice == "v":
                self._pager("最终代码", (self.last_result or {}).get("text") or "")
            elif choice == "j":
                self._pager("完整状态 (JSON)", self._json_dump())
            elif choice == "r":
                query = self.last_query
                self.last_result = None
                return self.new_task(prefill=query)
            else:
                return

    def _save_code(self) -> None:
        code = (self.last_result or {}).get("text") or ""
        if not code:
            self.console.print("[yellow]没有可保存的代码[/yellow]")
            return
        default = str(PROJECT_ROOT / "run" / f"sim_{time.strftime('%Y%m%d_%H%M%S')}.py")
        target = self.prompter.ask("保存到 › ", default=default).strip() or default
        path = Path(target).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        self.last_result["text"] = code
        self._write_code(path)

    def _json_dump(self) -> str:
        import json

        data = {k: v for k, v in (self.last_result or {}).items() if k != "kb_docs"}
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)

    def _pager(self, title: str, body: str) -> None:
        try:
            with self.console.pager(styles=True):
                self.console.print(f"[bold]{title}[/bold]\n")
                if title.endswith("JSON)"):
                    self.console.print(body, style="white", highlight=False)
                else:
                    self.console.print(Syntax(body or "# (空)", "python", line_numbers=True, word_wrap=True))
        except Exception:  # pragma: no cover - 非 TTY 时分页器不可用
            self.console.print(body)

    # -- 配置 ------------------------------------------------------------ #
    def edit_settings(self) -> None:
        while True:
            self.console.print()
            self.console.print(panels.config_panel(self.settings, show_secret=True))
            table = Table(box=panels.box.SIMPLE_HEAD, header_style="bold cyan")
            table.add_column("#", justify="right", width=3)
            table.add_column("变量")
            table.add_column("当前值")
            table.add_column("说明", style="dim")
            for i, field in enumerate(FIELDS, 1):
                value = getattr(self.settings, field.attr, None)
                table.add_row(str(i), field.key, _render_field_value(field, value, show_secret=True), field.help or field.label)
            self.console.print(Panel(table, title="[bold]可编辑项[/bold]", border_style="blue", box=panels.box.ROUNDED))

            raw = self.prompter.ask("输入编号修改，t 测连通性，v 校验配置，q 返回 › ").strip().lower()
            if raw in ("q", "", "quit"):
                return
            if raw in ("v", "check", "validate"):
                self.validate_settings()
                continue
            if raw in ("t", "test", "ping"):
                self.probe_api()
                continue
            try:
                field = FIELDS[int(raw) - 1]
            except (ValueError, IndexError):
                self.console.print("[red]无效编号[/red]")
                continue
            self._edit_field(field)

    def _edit_field(self, field: Field) -> None:
        current = getattr(self.settings, field.attr, None)
        if field.kind == "bool":
            self.console.print(f"[bold]{field.key}[/bold] 当前：{'开' if current else '关'}")
            new = self.prompter.choose("设为：", [("1", "开启"), ("0", "关闭")], default="1" if not current else "0")
            value = "1" if new == "1" else "0"
        elif field.kind == "choice":
            self.console.print(f"[bold]{field.key}[/bold] 可选：{' / '.join(field.choices)}")
            value = self.prompter.ask("新值 › ", default=str(current or field.choices[0])).strip()
            if value not in field.choices:
                self.console.print(f"[red]必须是 {field.choices} 之一[/red]")
                return
        elif field.secret:
            value = self.prompter.ask("新值（直接回车保持不变）› ").strip()
            if not value:
                return
        else:
            hint = "" if current in (None, "") else f"{current}"
            value = self.prompter.ask(f"新值（回车保持不变{('：' + hint) if hint else ''}）› ").strip()
            if not value:
                return
            if field.kind == "int":
                try:
                    int(value)
                except ValueError:
                    self.console.print("[red]需要整数[/red]")
                    return
            if field.kind == "float":
                try:
                    float(value)
                except ValueError:
                    self.console.print("[red]需要数值[/red]")
                    return

        env_path = PROJECT_ROOT / ".env"
        try:
            upsert_env(env_path, {field.key: value}, template=PROJECT_ROOT / ".env.example")
        except OSError as exc:
            self.console.print(f"[red]写入 .env 失败：{exc}[/red]")
            return
        os.environ[field.key] = value
        self.reload_settings()
        self.console.print(f"[green]已更新 {field.key} → {env_path}[/green]")

    def validate_settings(self) -> None:
        rows: list[tuple[str, str, str]] = []

        def add(label: str, ok: bool, detail: str) -> None:
            rows.append((label, "✅" if ok else "❌", detail))

        key = self.settings.openai_api_key or ""
        add("API Key", bool(key), "已配置" if key else "未配置（OPENAI_API_KEY / DEEPSEEK_API_KEY）")
        add("API 端点", True, self.settings.openai_base_url or "OpenAI 官方")
        kb = self.settings.resolved_kb_path()
        add("知识库", kb.exists(), f"{kb}（{kb.stat().st_size if kb.exists() else 0} 字节）")
        python = self.settings.exec_python or sys.executable
        add("执行解释器", Path(python).exists(), python)
        if self.settings.retrieval_backend == "openai":
            add("检索后端", True, "openai embedding（需要网络）")
        else:
            add("检索后端", True, "bm25（离线）")
        add("执行后端", self.settings.executor_backend in ("subprocess", "jupyter", "mcp", "auto"), self.settings.executor_backend)

        table = Table(box=panels.box.SIMPLE_HEAD, header_style="bold cyan")
        table.add_column("检查项")
        table.add_column("", justify="center", width=2)
        table.add_column("详情", style="dim")
        for label, mark, detail in rows:
            table.add_row(label, mark, detail)
        self.console.print(Panel(table, title="[bold]配置自检[/bold]", border_style="blue", box=panels.box.ROUNDED))
        self.console.print("[dim]这里只查本地配置；想验证 API 是否真的通，按 t 发一个最小请求。[/dim]")

    def probe_api(self, *, timeout: float = 20.0) -> bool:
        """发一个最小请求验证 API 连通性 —— 免得跑完整流程才发现网络不通。"""
        from .llm import probe_api

        if not self.settings.openai_api_key:
            self.console.print(panels.error_panel("连通性测试失败", RuntimeError(
                "未配置 API Key：请在「运行配置」里设置 OPENAI_API_KEY（或 DEEPSEEK_API_KEY）。"
            )))
            return False

        model = self.settings.analyst_model
        endpoint = self.settings.openai_base_url or "https://api.openai.com/v1"
        self.console.print(f"[dim]正在向 {endpoint} 发送最小请求（模型 {model}，超时 {timeout:g}s）…[/dim]")
        ok, payload, elapsed = probe_api(self.settings, model=model, timeout=timeout)
        if not ok:
            self.console.print(panels.error_panel("API 连通性测试失败", payload))
            return False

        reply = panels.clip(str(payload).replace("\n", " "), 160)
        self.console.print(Panel(
            Text.from_markup(
                f"API 连通 ✅  模型 [bold]{model}[/bold] · 往返 {elapsed:.2f}s\n"
                f"[dim]返回：{reply}[/dim]"
            ),
            title="[bold]API 连通性测试[/bold]",
            border_style="green",
            box=panels.box.ROUNDED,
        ))
        return True

    # -- 知识库 ---------------------------------------------------------- #
    def show_kb(self) -> None:
        self.console.print()
        self.console.print(panels.kb_overview_panel(self.settings.resolved_kb_path()))
        if self.prompter.confirm("搜索知识库？", default=False):
            keyword = self.prompter.ask("关键词 › ").strip()
            self.search_kb(keyword)

    def search_kb(self, keyword: str) -> None:
        from .knowledge import build_retriever

        if not keyword:
            return
        try:
            settings = self.settings
            retriever = build_retriever(settings)
            docs = retriever.invoke(keyword)
        except Exception as exc:  # noqa: BLE001 - 检索失败不该影响 CLI
            self.console.print(f"[red]检索失败：{exc}[/red]")
            return
        blocks: list[Any] = [Text(f"关键词：{keyword} · top_k={self.settings.top_k}", style="dim")]
        for i, doc in enumerate(docs, 1):
            meta = getattr(doc, "metadata", {}) or {}
            heading = meta.get("heading") or meta.get("source") or f"片段 {i}"
            body = panels.clip(getattr(doc, "page_content", ""), 1200)
            blocks.append(Panel(Text(body, overflow="fold"), title=f"[bold]{i}. {heading}[/bold]", border_style="blue", box=panels.box.ROUNDED))
        self.console.print(Group(*blocks))

    # -- 历史 ------------------------------------------------------------ #
    def show_history(self) -> None:
        records = load_records(self.hist_file)
        self.console.print()
        if not records:
            self.console.print(Panel(Text("还没有历史记录。跑一次任务就会写进 " + str(self.hist_file), style="dim"),
                                     title="[bold]历史记录[/bold]", border_style="blue", box=panels.box.ROUNDED))
            return
        self.console.print(Panel(panels.history_table(records[:30]), title="[bold]历史记录[/bold]",
                                 subtitle=f"最近 {min(len(records), 30)} / {len(records)} 条 · {self.hist_file}",
                                 border_style="blue", box=panels.box.ROUNDED))
        while True:
            raw = self.prompter.ask("输入编号查看详情，c 清空历史，q 返回 › ").strip().lower()
            if raw in ("q", "", "quit"):
                return
            if raw in ("c", "clear"):
                if self.prompter.confirm("确认清空全部历史？", default=False):
                    clear_records(self.hist_file)
                    self.console.print("[green]已清空[/green]")
                return
            try:
                record = records[int(raw) - 1]
            except (ValueError, IndexError):
                self.console.print("[red]无效编号[/red]")
                continue
            self.console.print(panels.history_detail(record))
            if record.get("code") and self.prompter.confirm("把当时的代码另存为文件？", default=False):
                self.last_result = {"text": record.get("code", "")}
                self._save_code()

    # -- 帮助 ------------------------------------------------------------ #
    def show_help(self) -> None:
        body = Text.from_markup(
            "[bold]这是什么[/bold]\n"
            "  把自然语言仿真需求变成可运行的 jwave 代码：需求分析 → 知识检索 → 参数提取\n"
            "  → 物理预检 → 生成 → 静态检查 → 执行 → 语义数值门 → 输出。\n\n"
            "[bold]三道关[/bold]\n"
            "  方案一 参数物理预检（生成前，纯算术：每波长网格点 / Nyquist / PML …）\n"
            "  方案二 AST 静态检查（执行前，把知识库里「常编造的 API」变成可执行规则）\n"
            "  方案三 语义数值门（执行后，要求打印 __JWAVE_SELFCHECK__ 并校验 |p|max 等）\n\n"
            "[bold]输入命令（在需求输入框里直接敲）[/bold]\n"
            "  [cyan]:help[/]      显示本页          [cyan]:settings[/] 打开配置编辑器\n"
            "  [cyan]:kb[/]        知识库概览/检索    [cyan]:history[/]  历史记录\n"
            "  [cyan]:preset[/]    用内置示例需求     [cyan]@req.txt[/]  从文件读取需求\n"
            "  [cyan]:q[/]         取消当前输入\n\n"
            "[bold]非交互用法[/bold]\n"
            "  jwave_flow \"生成一个 128x128 的二维时域声学仿真…\"\n"
            "  jwave_flow \"…\" --json --out sim.py     # 脚本/CI 友好\n\n"
            "[dim]配置写在项目根的 .env；全部可选项见 .env.example。[/dim]"
        )
        self.console.print(Panel(body, title="[bold]使用说明[/bold]", border_style="cyan", box=panels.box.ROUNDED))


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def build_parser():
    import argparse

    p = argparse.ArgumentParser(prog="jwave-tui", description="jwave 仿真工作流 · 交互式 CLI")
    p.add_argument("query", nargs="?", help="可选：预设的自然语言需求（进入界面后仍可确认/修改）")
    p.add_argument("--kb", type=Path, help="知识库 markdown 路径")
    p.add_argument("--top-k", type=int, help="知识检索命中数量")
    p.add_argument("--retrieval", choices=["bm25", "openai"], help="检索后端")
    p.add_argument("--backend", choices=["subprocess", "jupyter", "mcp", "auto"], help="代码执行后端")
    p.add_argument("--max-iterations", type=int, help="执行/纠错最大轮数")
    p.add_argument("--model", help="同时覆盖 analyst/coder 模型名")
    return p


def overrides_from_args(args) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
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
    return overrides


def run_tui(
    overrides: dict[str, Any] | None = None,
    *,
    console: "Console | None" = None,
    initial_query: str = "",
    auto_out: Path | None = None,
) -> int:
    if not RICH_AVAILABLE:
        print(
            "交互式界面需要 rich（以及可选的 prompt_toolkit）：\n"
            "    pip install rich prompt_toolkit\n"
            "或改用非交互模式：jwave_flow \"你的需求\"",
            file=sys.stderr,
        )
        return 2
    settings = Settings.from_env(**(overrides or {}))
    app = TuiApp(
        settings, overrides=overrides, console=console, initial_query=initial_query, auto_out=auto_out
    )
    try:
        return app.run()
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - 最后一道网：CLI 不应该以 traceback 收场
        if os.environ.get("JWAVE_DEBUG"):
            raise
        from .errors import format_error_text

        print(f"\n界面遇到未预期的错误：\n  {format_error_text(exc, settings=settings)}", file=sys.stderr)
        print("（设置 JWAVE_DEBUG=1 可查看完整 traceback）", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_tui(overrides_from_args(args), initial_query=(args.query or "").strip())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
