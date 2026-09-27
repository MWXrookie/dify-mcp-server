"""The Dify "仿真" workflow, rebuilt with LangGraph.

Node order (identical to the Dify graph)::

    START → 需求分析 → 知识检索 → 模板转换 → 参数提取 → 代码生成 → 执行
                                                     ▲            │
                                                     │       stderr 为空?
                          代码纠错 ←──────── 否 ──────┘            │是
                                                            输出 → END

The Dify ``loop`` node (``loop_count = 10``) is expressed as a LangGraph cycle
that is capped by ``settings.max_iterations``.
"""
from __future__ import annotations

import sys
import time
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from .config import Settings
from .executor import BaseExecutor, get_executor
from .knowledge import build_retriever, render_template_transform
from .physics import check_params
from .semantic import SELFCHECK_CONTRACT, check_semantics
from .static_check import check_code
from .llm import GeneratedCode, FixedCode, build_chat_model, invoke_code_llm
from .prompts import (
    code_fix_prompt,
    code_generate_prompt,
    param_extract_prompt,
    requirement_analyst_prompt,
)
from .state import WorkflowState


def _as_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(content)


class SimulationWorkflow:
    """Owns the (reusable) LLM / retriever / executor resources."""

    def __init__(
        self,
        settings: Settings,
        *,
        analyst_llm: Any | None = None,
        coder_llm: Any | None = None,
        retriever: Any | None = None,
        executor: BaseExecutor | None = None,
    ):
        self.settings = settings
        self.analyst_llm = analyst_llm or build_chat_model(settings, settings.analyst_model)
        self.coder_llm = coder_llm or build_chat_model(settings, settings.coder_model)
        self.retriever = retriever or build_retriever(settings)
        self.executor = executor or get_executor(settings)
        self.graph = self._build()

    # -- nodes --------------------------------------------------------- #
    def _log(self, state: WorkflowState, message: str) -> list[str]:
        trace = list(state.get("trace") or [])
        trace.append(message)
        if self.settings.verbose:
            # stderr: keeps `--json` output on stdout machine-readable
            print(f"  · {message}", file=sys.stderr, flush=True)
        return trace

    def n_analyze(self, state: WorkflowState) -> dict:
        prompt = requirement_analyst_prompt().format_messages(query=state["query"])
        requirement = _as_text(self.analyst_llm.invoke(prompt))
        return {"requirement": requirement, "trace": self._log(state, "① 需求分析 完成")}

    def n_retrieve(self, state: WorkflowState) -> dict:
        docs = self.retriever.invoke(state["query"])
        return {
            "kb_docs": docs,
            "trace": self._log(state, f"② 知识检索 命中 {len(docs)} 个片段"),
        }

    def n_template(self, state: WorkflowState) -> dict:
        context = render_template_transform(state.get("kb_docs") or [])
        return {"kb_context": context, "trace": self._log(state, f"③ 模板转换 {len(context)} 字符")}

    def n_extract(self, state: WorkflowState) -> dict:
        messages = param_extract_prompt().format_messages(
            query=state["query"], kb_context=state.get("kb_context", "")
        )
        # 方案一：如果上一轮物理预检没通过，把问题回灌，让模型修正参数
        previous = state.get("param_issues") or []
        if previous:
            messages = list(messages) + [
                HumanMessage(
                    content=(
                        "你上一次输出的参数没有通过物理预检，请**只重新输出修正后的 JSON**：\n"
                        + "\n".join(previous)
                    )
                )
            ]
        params = _as_text(self.analyst_llm.invoke(messages))
        return {"params_json": params, "trace": self._log(state, "④ 参数提取 完成")}

    def n_param_check(self, state: WorkflowState) -> dict:
        """④b 参数物理预检（方案一）——纯算术，不调用模型。"""
        if not self.settings.param_check_enabled:
            return {"param_check_ok": True, "trace": self._log(state, "④b 参数预检 已关闭")}

        result = check_params(state.get("params_json", ""), self.settings)
        rounds = int(state.get("param_check_rounds", 0)) + 1
        errors = [i.render() for i in result.errors]
        warnings = [i.render() for i in result.warnings]

        if result.ok:
            detail = f"，{len(warnings)} 条告警" if warnings else ""
            note = f"④b 参数预检 通过{detail}"
        else:
            note = f"④b 参数预检 未通过（{len(errors)} 个错误，第 {rounds} 轮）"
        for line in warnings:
            if self.settings.verbose:
                print(f"    {line}", file=sys.stderr, flush=True)
        return {
            "param_check_ok": result.ok,
            "param_check_rounds": rounds,
            "param_issues": errors,
            "param_warnings": warnings,
            "param_constraints": result.constraints,
            "param_check_report": result.to_dict(),
            "trace": self._log(state, note),
        }

    def _route_after_param_check(self, state: WorkflowState) -> str:
        """不合格就不进入代码生成，先回退到参数提取重试。"""
        if state.get("param_check_ok"):
            return "generate"
        if int(state.get("param_check_rounds", 0)) >= self.settings.param_check_max_rounds:
            if self.settings.verbose:
                print(
                    f"  ! 参数预检重试 {self.settings.param_check_max_rounds} 轮仍未通过，"
                    "带着约束继续生成（结果未经参数校验）",
                    file=sys.stderr, flush=True,
                )
            return "generate"
        return "retry"

    def n_generate(self, state: WorkflowState) -> dict:
        messages = code_generate_prompt().format_messages(
            query=state["query"], code_ref=state.get("params_json", "")
        )
        # 方案一：把物理约束/告警一起交给代码生成，从上游避免欠采样等问题
        constraints = list(state.get("param_constraints") or [])
        warnings = list(state.get("param_warnings") or [])
        if constraints or warnings:
            extra = []
            if constraints:
                extra.append("必须满足以下物理约束：\n" + "\n".join(f"- {c}" for c in constraints))
            if warnings:
                extra.append("注意以下参数问题：\n" + "\n".join(f"- {w}" for w in warnings))
            messages = list(messages) + [HumanMessage(content="\n\n".join(extra))]
        messages = list(messages) + [HumanMessage(content=SELFCHECK_CONTRACT)]
        prompt = messages
        code = invoke_code_llm(self.coder_llm, prompt, GeneratedCode, ["code"])
        return {
            "code": code,
            "code_final": code,
            "iterations": 0,
            "trace": self._log(
                state,
                f"⑤ 代码生成 {len(code)} 字符"
                + ("（已注入参数约束）" if (state.get("param_constraints") or state.get("param_warnings")) else ""),
            ),
        }

    def n_static_check(self, state: WorkflowState) -> dict:
        """⑤b AST 静态规则检查（方案二）——纯 AST，不调用模型、不执行代码。"""
        if not self.settings.static_check_enabled:
            return {"trace": self._log(state, "⑤b 静态检查 已关闭")}

        code = state.get("code_final", "")
        report = check_code(code)
        rounds = int(state.get("static_rounds", 0)) + 1
        issues = [i.render() for i in report.issues]
        if report.parse_error:
            issues = [report.feedback()]

        out: dict = {
            "static_issues": issues,
            "static_rounds": rounds,
            "static_report": report.to_dict(),
        }
        if issues:
            # 复用「代码纠错」节点：把静态报告作为它的“报错”输入。
            # 注意写 fix_reason 而不是 stderr —— stderr 要保留真实执行错误。
            out["fix_reason"] = "静态规则检查未通过：\n" + "\n".join(f"- {i}" for i in issues)
            note = f"⑤b 静态检查 发现 {len(issues)} 处问题（第 {rounds} 轮）"
        else:
            note = "⑤b 静态检查 通过"
        out["trace"] = self._log(state, note)
        return out

    def _route_after_static(self, state: WorkflowState) -> str:
        if not state.get("static_issues"):
            return "run"
        if int(state.get("static_rounds", 0)) >= self.settings.max_iterations:
            if self.settings.verbose:
                print("  ! 静态问题修复达上限，仍执行一次", file=sys.stderr, flush=True)
            return "run"
        return "fix"

    def n_run(self, state: WorkflowState) -> dict:
        code = state.get("code_final", "")
        result = self.executor.run(code)
        iterations = int(state.get("iterations", 0)) + 1
        status = "通过 ✅" if result.ok else "报错 ❌"
        return {
            **result.to_dict(),
            "success": result.ok,
            "last_error": "" if result.ok else result.stderr,
            "fix_reason": "",
            "iterations": iterations,
            "trace": self._log(
                state,
                f"⑥ 执行(第 {iterations} 次, {result.backend}) {status} "
                f"[{result.execution_time:.2f}s]",
            ),
        }

    def n_semantic_gate(self, state: WorkflowState) -> dict:
        """⑥b 语义数值门（方案三）——解析自检行并做确定性判据。"""
        if not self.settings.semantic_check_enabled:
            return {"verified": True, "trace": self._log(state, "⑥b 语义门 已关闭")}

        # 运行本身就没通过时，不要谎报“缺少自检行”，如实反映执行失败
        if not state.get("success"):
            raw = (state.get("stderr") or state.get("last_error") or "").strip()
            tail = raw.splitlines()[-1] if raw else ""
            issues = [f"执行失败：{tail}" if tail else "执行失败（没有任何错误输出）"]
            return {
                "semantic_issues": issues,
                "selfcheck": {},
                "verified": False,
                "fix_reason": raw or "执行失败且无输出",
                "trace": self._log(state, f"⑥b 语义门 未通过（运行失败：{tail or '无输出'}）"),
            }

        expected = (state.get("param_check_report") or {}).get("scalars", {})
        report = check_semantics(state.get("stdout", ""), self.settings, expected=expected)
        issues = list(report.issues)

        out: dict = {
            "semantic_issues": issues,
            "selfcheck": report.data,
            "verified": report.ok,
        }
        if issues:
            out["fix_reason"] = report.feedback()
            note = f"⑥b 语义门 未通过（{len(issues)} 项）"
        else:
            note = "⑥b 语义门 通过"
            if report.data:
                abs_max = report.data.get("abs_max")
                if isinstance(abs_max, (int, float)):
                    note += f"（|p|max={abs_max:g}）"
        out["trace"] = self._log(state, note)
        return out

    def _route_after_semantic(self, state: WorkflowState) -> str:
        if state.get("verified"):
            return "finalize"
        if int(state.get("iterations", 0)) >= self.settings.max_iterations:
            if self.settings.verbose:
                print(
                    f"  ! 达到最大迭代次数 {self.settings.max_iterations}，"
                    "输出当前代码（**未通过语义校验**）",
                    file=sys.stderr, flush=True,
                )
            return "finalize"
        return "fix"

    def n_fix(self, state: WorkflowState) -> dict:
        reason = state.get("fix_reason") or state.get("stderr", "")
        messages = code_fix_prompt().format_messages(
            code_final=state.get("code_final", ""),
            context=state.get("kb_context", ""),
            stderr=reason,
        )
        messages = list(messages) + [HumanMessage(content=SELFCHECK_CONTRACT)]
        fixed = invoke_code_llm(self.coder_llm, messages, FixedCode, ["code_2", "code"])
        return {
            "code_final": fixed,
            "trace": self._log(state, f"⑦ 代码纠错 {len(fixed)} 字符"),
        }

    def n_finalize(self, state: WorkflowState) -> dict:
        verified = bool(state.get("verified"))
        note = "⑧ 输出" + ("" if verified else "（未通过语义校验 ⚠️）")
        if self.settings.verbose and not verified:
            print(
                "  ⚠️ 最终产物未通过语义数值门，请人工确认（可用 --json 查看 semantic_issues）",
                file=sys.stderr, flush=True,
            )
        return {"text": state.get("code_final", ""), "verified": verified, "trace": self._log(state, note)}

    # -- routing ------------------------------------------------------- #
    def _route_after_run(self, state: WorkflowState) -> str:
        """运行失败 -> 纠错；运行成功 -> 交给语义数值门。"""
        if state.get("success"):
            return "gate"
        if int(state.get("iterations", 0)) >= self.settings.max_iterations:
            return "gate"          # 交给语义门统一给出结论（避免重复打印）
        return "fix"

    # -- assembly ------------------------------------------------------ #
    def _build(self):
        g = StateGraph(WorkflowState)
        g.add_node("analyze", self.n_analyze)
        g.add_node("retrieve", self.n_retrieve)
        g.add_node("template", self.n_template)
        g.add_node("extract", self.n_extract)
        g.add_node("param_check", self.n_param_check)
        g.add_node("generate", self.n_generate)
        g.add_node("static_check", self.n_static_check)
        g.add_node("run_code", self.n_run)
        g.add_node("semantic_gate", self.n_semantic_gate)
        g.add_node("fix_code", self.n_fix)
        g.add_node("finalize", self.n_finalize)

        g.add_edge(START, "analyze")
        g.add_edge("analyze", "retrieve")
        g.add_edge("retrieve", "template")
        g.add_edge("template", "extract")
        g.add_edge("extract", "param_check")
        g.add_conditional_edges(
            "param_check",
            self._route_after_param_check,
            {"generate": "generate", "retry": "extract"},
        )
        g.add_edge("generate", "static_check")
        g.add_conditional_edges(
            "static_check", self._route_after_static, {"run": "run_code", "fix": "fix_code"}
        )
        g.add_conditional_edges(
            "run_code", self._route_after_run, {"fix": "fix_code", "gate": "semantic_gate"}
        )
        g.add_conditional_edges(
            "semantic_gate",
            self._route_after_semantic,
            {"fix": "fix_code", "finalize": "finalize"},
        )
        g.add_edge("fix_code", "static_check")
        g.add_edge("finalize", END)
        return g.compile()

    # -- public API ---------------------------------------------------- #
    def invoke(self, query: str, **kwargs) -> WorkflowState:
        start = time.time()
        state: WorkflowState = {
            "query": query, "trace": [], "iterations": 0, "param_check_rounds": 0,
            "static_rounds": 0, "fix_reason": "", "last_error": "",
        }
        out = self.graph.invoke(state, **kwargs)
        out["elapsed"] = time.time() - start  # type: ignore[index]
        return out

    def stream(self, query: str, **kwargs):
        yield from self.graph.stream(
            {"query": query, "trace": [], "iterations": 0, "param_check_rounds": 0, "static_rounds": 0, "fix_reason": "", "last_error": ""}, **kwargs
        )

    def close(self) -> None:
        self.executor.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def run_workflow(query: str, settings: Settings | None = None, **kwargs) -> WorkflowState:
    """Convenience one-shot entry point."""
    settings = settings or Settings.from_env()
    with SimulationWorkflow(settings) as wf:
        return wf.invoke(query, **kwargs)
