"""End-to-end run of the graph with a stub LLM (no API key required)."""
from __future__ import annotations

import json
from pathlib import Path

from jwave_flow.config import Settings
from jwave_flow.graph import SimulationWorkflow

ROOT = Path(__file__).resolve().parent.parent

BUGGY = "import sys\nprint('simulating')\nsys.stderr.write('ValueError: bad positions\\n')\n"
# 结构取自「参数提取」节点的真实输出（含频率与仿真时长）
GOOD_PARAMS = json.dumps(
    {
        "grid_size": [64, 64],
        "medium": {"sound_speed": 1500.0},
        "source": {"type": "point", "frequency": 5e6},
        "simulation_time": 2e-5,
    }
)
BAD_PARAMS = json.dumps({"medium": {"sound_speed": 1500.0}})  # 缺频率 -> 预检报错
SELFCHECK_OK = (
    "import json\n"
    "print('simulation ok')\n"
    "print(\"__JWAVE_SELFCHECK__\" + json.dumps("
    "{'finite': True, 'abs_max': 42.0, 'shape': [10, 8, 8, 1], "
    "'dt': 1e-8, 'f0': 5e6}))\n"
)
FIXED = SELFCHECK_OK
# 能跑、但没有自检行 -> 方案三应当拦下来
NO_SELFCHECK = "print('simulation ok')\n"
# 能跑、自检行也在，但场几乎是零 -> 方案三应当拦下来
ZERO_FIELD = (
    "import json\n"
    "print(\"__JWAVE_SELFCHECK__\" + json.dumps("
    "{'finite': True, 'abs_max': 0.0, 'shape': [10, 8, 8, 1]}))\n"
)
# 方案二：tone_burst 传了 dt + 对压力场二次转换
STATIC_BAD = (
    "import jax.numpy as jnp\n"
    "dt = 1e-8\n"
    "sig = tone_burst(time_axis.dt, 5e6, 3)\n"
    "rho = jw.simulate_wave_propagation(medium, time_axis, sources=sources)\n"
    "p = jw.pressure_from_density(rho, medium)\n"
)



class _Msg:
    def __init__(self, content):
        self.content = content


def _prompt_text(prompt) -> str:
    if isinstance(prompt, str):
        return prompt
    if hasattr(prompt, "to_string"):
        return prompt.to_string()
    return "\n".join(getattr(m, "content", str(m)) for m in prompt)


class FakeLLM:
    """Returns canned answers keyed off the prompt, like the real nodes would."""

    def __init__(self, gen_code=BUGGY, fixed=FIXED, params=GOOD_PARAMS):
        self.gen_code = gen_code
        self.fixed = fixed
        # a list is consumed in order (used to simulate a first, bad extraction)
        self.params = list(params) if isinstance(params, list) else [params]
        self.seen: list[str] = []

    def invoke(self, prompt):
        text = _prompt_text(prompt)
        self.seen.append(text)
        if "需求分析师" in text:
            return _Msg("需求描述：一个二维时域声学仿真。")
        if "参数提取器" in text:
            return _Msg(self.params.pop(0) if len(self.params) > 1 else self.params[0])
        if "代码生成器" in text:
            return _Msg(self.gen_code)
        if "代码改正器" in text:
            return _Msg(self.fixed)
        raise AssertionError(f"unexpected prompt: {text[:80]}")

    def with_structured_output(self, schema, **kwargs):
        raise NotImplementedError("stub: force the text fallback path")


def _settings(**kw):
    return Settings.from_env(
        kb_path=ROOT / "kb" / "jwave_kb_organized.md",
        executor_backend="subprocess",
        retrieval_backend="bm25",
        verbose=False,
        **kw,
    )


def test_loop_repairs_broken_code_and_succeeds():
    settings = _settings(max_iterations=10)
    llm = FakeLLM()
    with SimulationWorkflow(settings, analyst_llm=llm, coder_llm=llm) as wf:
        out = wf.invoke("做个二维时域仿真")

    assert out["iterations"] == 2           # 1 failing run + 1 repair
    assert out["success"] is True
    assert out["verified"] is True
    assert out["text"] == FIXED.rstrip("\n")
    trace = "\n".join(out["trace"])
    for marker in ["① 需求分析", "② 知识检索", "③ 模板转换", "④ 参数提取",
                   "⑤ 代码生成", "⑥ 执行", "⑦ 代码纠错", "⑧ 输出"]:
        assert marker in trace
    # the knowledge base was actually retrieved and injected (参数提取 prompt)
    assert any("知识库参考：" in p and "###" in p for p in llm.seen)


def test_loop_gives_up_after_max_iterations():
    settings = _settings(max_iterations=2)
    llm = FakeLLM(gen_code=BUGGY, fixed=BUGGY)  # repair keeps failing
    with SimulationWorkflow(settings, analyst_llm=llm, coder_llm=llm) as wf:
        out = wf.invoke("做个二维时域仿真")

    assert out["iterations"] == 2           # capped at loop_count
    assert out["success"] is False
    assert out["text"] == BUGGY.rstrip("\n")


def test_param_check_retries_extraction_before_codegen():
    """方案一：参数不合格时不进入代码生成，而是回退重试「参数提取」。"""
    settings = _settings(max_iterations=10)
    llm = FakeLLM(params=[BAD_PARAMS, GOOD_PARAMS])   # 第一次缺频率，第二次修好
    with SimulationWorkflow(settings, analyst_llm=llm, coder_llm=llm) as wf:
        out = wf.invoke("做个二维时域仿真")

    assert out["param_check_ok"] is True
    assert out["param_check_rounds"] == 2             # 第一轮失败，第二轮通过
    assert out["success"] is True
    trace = "\n".join(out["trace"])
    assert "④b 参数预检 未通过" in trace
    assert "④b 参数预检 通过" in trace
    # 修正参数时确实把问题回灌给了模型
    assert any("没有通过物理预检" in p for p in llm.seen)


def test_param_check_injects_dx_constraint_into_codegen():
    """没有 dx 时应反算上限，并在「代码生成」提示词里注入约束。"""
    settings = _settings()
    llm = FakeLLM()
    with SimulationWorkflow(settings, analyst_llm=llm, coder_llm=llm) as wf:
        out = wf.invoke("做个二维时域仿真")

    assert out["param_constraints"] and "dx ≤" in out["param_constraints"][0]
    assert any("网格间距必须满足 dx ≤" in p for p in llm.seen)


def test_semantic_gate_rejects_code_without_selfcheck():
    """方案三：能跑但没有自检行 -> 不算通过。"""
    settings = _settings(max_iterations=2)
    llm = FakeLLM(fixed=NO_SELFCHECK)
    with SimulationWorkflow(settings, analyst_llm=llm, coder_llm=llm) as wf:
        out = wf.invoke("做个二维时域仿真")

    assert out["verified"] is False
    assert any("找不到自检行" in i for i in out["semantic_issues"])
    assert "未通过语义校验" in "\n".join(out["trace"])


def test_semantic_gate_rejects_all_zero_field():
    """方案三：自检行在，但 |p|max 为 0 -> 激励没起作用，不算通过。"""
    settings = _settings(max_iterations=2)
    llm = FakeLLM(fixed=ZERO_FIELD)
    with SimpleWorkflowFactory(settings, llm) as wf:
        out = wf.invoke("做个二维时域仿真")
    assert out["verified"] is False
    assert any("几乎全零" in i for i in out["semantic_issues"])


class SimpleWorkflowFactory(SimulationWorkflow):
    """小工具：同一个 fake LLM 同时当 analyst 与 coder。"""

    def __init__(self, settings, llm):
        super().__init__(settings, analyst_llm=llm, coder_llm=llm)


def test_static_rule_catches_known_bugs_before_execution():
    """方案二：静态规则在**执行之前**就能抓到 tone_burst(dt) 与二次转换。"""
    settings = _settings(max_iterations=4)
    llm = FakeLLM(gen_code=STATIC_BAD, fixed=FIXED)
    with SimulationWorkflow(settings, analyst_llm=llm, coder_llm=llm) as wf:
        out = wf.invoke("做个二维时域仿真")

    # 关键：有问题的代码**一次都没被执行**（静态拦下 -> 直接纠错）
    assert out["iterations"] == 1
    assert out["static_rounds"] == 2            # 第 1 轮发现问题，第 2 轮通过
    assert "⑤b 静态检查 发现 2 处问题" in "\n".join(out["trace"])
    # 实际被拦下的两类问题
    assert out["static_report"]["ok"] is True    # 最终状态里的报告是修复后的
    assert out["verified"] is True
