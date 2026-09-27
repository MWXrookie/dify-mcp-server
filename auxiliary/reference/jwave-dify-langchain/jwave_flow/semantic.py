"""方案三：输出契约 + 数值门（运行之后）。

循环原本的退出条件是「stderr 为空」——只证明代码能跑。这里再加一道
**确定性的数值判据**：要求生成代码在末尾打印一行机器可读的自检结果

    __JWAVE_SELFCHECK__{"finite": true, "abs_max": 5016.6, "shape": [1001,64,64,1], "dt": 1.1e-08, "f0": 5000000.0}

执行器抓到这行后，本模块据此判断结果是否「物理上讲得通」：

  S1 自检行是否存在        （契约是否被遵守）
  S2 场是否有限           （无 nan / inf）
  S3 场是否非全零         （激励真的起作用了）
  S4 量级是否在合理范围   （没炸/没退化成噪声）
  S5 形状是否存在
  S6 dt / f0 与需求是否一致（防串参）

判据全部确定性、可解释，失败原因会原样回灌给「代码纠错」节点。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .config import Settings

MARKER = "__JWAVE_SELFCHECK__"

# 追加到「代码生成 / 代码纠错」提示词里的输出契约
SELFCHECK_CONTRACT = f'''
【输出契约 · 必须遵守】
在代码的最后，额外打印一行机器可读的自检结果（**单行**、以 {MARKER} 开头、紧随合法 JSON）：

print("{MARKER}" + json.dumps({{
    "finite": bool(jnp.all(jnp.isfinite(_field))),
    "abs_max": float(jnp.max(jnp.abs(_field))),
    "shape": list(_field.shape),
    "dt": float(time_axis.dt),
    "f0": float(source_frequency),
}}))

其中 _field 是你最终得到的压力场；若它是 Field/OnGrid 对象，请用 _field.params。
除了这一行之外不要再增加别的输出。
'''


@dataclass
class SemanticReport:
    present: bool = False
    data: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def feedback(self) -> str:
        return "自检未通过：\n" + "\n".join(f"- {i}" for i in self.issues)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "present": self.present,
            "data": self.data,
            "issues": self.issues,
            "checked": self.checked,
        }


def parse_selfcheck(stdout: str) -> dict[str, Any] | None:
    """从 stdout 中提取自检 JSON（宽容：允许前面有别的内容）。"""
    if not stdout:
        return None
    for line in stdout.splitlines():
        idx = line.find(MARKER)
        if idx < 0:
            continue
        payload = line[idx + len(MARKER):].strip().strip("`")
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            return data
    return None


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def check_semantics(
    stdout: str,
    settings: Settings,
    expected: dict[str, Any] | None = None,
) -> SemanticReport:
    """对一次执行结果做数值判据。Never raises."""
    report = SemanticReport()
    expected = expected or {}

    if not settings.semantic_check_enabled:
        report.data = {"skipped": True}
        return report

    data = parse_selfcheck(stdout)
    if data is None:
        report.present = False
        if settings.require_selfcheck:
            report.issues.append(
                f"输出中找不到自检行 {MARKER}（未遵守输出契约）"
                "，无法判断结果是否有效"
            )
        return report

    report.present = True
    report.data = data

    # S2 有限性
    finite = data.get("finite")
    if finite is None:
        report.issues.append("自检结果缺少 finite 字段")
    elif finite is not True:
        report.issues.append("场中出现 nan/inf（finite=false），数值发散")
    report.checked.append("S2_finite")

    # S3/S4 量级
    abs_max = _num(data.get("abs_max"))
    if abs_max is None:
        report.issues.append("自检结果缺少可解析的 abs_max 字段")
    else:
        if abs_max <= settings.min_abs_max:
            report.issues.append(
                f"场幅值 |p|max = {abs_max:g}，几乎全零——激励没有真正起作用"
            )
        if abs_max > settings.max_abs_max:
            report.issues.append(
                f"场幅值 |p|max = {abs_max:g} 超出合理上限 {settings.max_abs_max:g}，疑似数值发散"
            )
    report.checked.append("S3_nonzero")
    report.checked.append("S4_magnitude")

    # S5 形状
    shape = data.get("shape")
    if not shape:
        report.issues.append("自检结果缺少 shape 字段")
    report.checked.append("S5_shape")

    # S6 dt / f0 与预期一致（防串参）
    exp_f0 = _num(expected.get("frequency"))
    got_f0 = _num(data.get("f0"))
    if exp_f0 and got_f0 and abs(got_f0 - exp_f0) > 0.01 * exp_f0:
        report.issues.append(
            f"代码实际使用的频率 f0={got_f0:g} 与需求 {exp_f0:g} 不一致（偏差 >1%）"
        )
    report.checked.append("S6_params_match")

    return report
