"""结果分析模块（T-007）· analyze_simulation_result MCP 工具。

职责
----
读取仿真 stdout 中的压力场 JSON（约定标记 `__ACOU_FIELD_START__/__ACOU_FIELD_END__`），
计算物理量摘要、生成热力图/波形图（PNG → base64），并按物理合理性给出 verdict。

verdict 判定口径（对标 docs/VALIDATION_BASELINE.md · VAL-1 验证基准集）
---------------------------------------------------------------------
- "abnormal"  : 执行失败 / 无压力场数据 / 含 NaN/Inf / 疑似数值发散（幅值超物理上限）
- "zero_field": 场全零（Sources 坐标错误、p0 误用等典型故障，见 VAL-1 与纠错速查表）
- "normal"    : 以上均未触发

依赖策略
--------
numpy/matplotlib 懒加载（网关镜像已含）；任一项不可用时自动降级：
- 无 matplotlib → ASCII 热力图（字符密度表示幅值）
- 无 numpy     → 纯 Python 计算物理量
保证工具在任何环境下不因缺依赖而崩溃。
"""

import base64
import io
import json
import math
import os
import re
from typing import Any

# matplotlib 在只读 HOME（容器）下无法建 ~/.config，强制使用可写缓存目录
os.environ.setdefault("MPLCONFIGDIR", "/tmp")

try:  # numpy 为可选（纯 Python 降级）
    import numpy as _np
except Exception:  # noqa: BLE001
    _np = None

try:  # matplotlib 为可选（ASCII 热力图降级）
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as _plt
except Exception:  # noqa: BLE001
    _plt = None

# 场数据输出约定：仿真代码在 stdout 打印以下标记包裹的 JSON
_FIELD_START = "__ACOU_FIELD_START__"
_FIELD_END = "__ACOU_FIELD_END__"

# 可注入仿真代码末尾的"场数据输出"模板（T-008 接入 Dify 工作流时复制即用；
# 也可由 LLM 依据该模板自行生成）。输出"全时最大绝对压力场"，避免 t=0 全零帧陷阱。
FIELD_OUTPUT_SNIPPET = '''\
import json as __json
import jax.numpy as __jnp
__field = __jnp.max(__jnp.abs(p.params), axis=0)[..., 0]  # 全时最大 |p| 场 (Nx, Ny)
print("__ACOU_FIELD_START__")
print(__json.dumps({"shape": list(__field.shape), "kind": "field", "data": __field.tolist()}))
print("__ACOU_FIELD_END__")
print(f"最大压力: {float(__jnp.max(__field)):.6f}")
'''

# 物理发散阈值：声压超过该量级视为数值发散（超声非线性/空化远低于此）
_PHYSICAL_MAX_PRESSURE_PA = 1e12


def _extract_field(stdout: str) -> dict | None:
    """从 stdout 提取压力场 JSON（标记包裹）。"""
    if not stdout:
        return None
    m = re.search(
        re.escape(_FIELD_START) + r"\s*(\{.*?\})\s*" + re.escape(_FIELD_END),
        stdout,
        re.DOTALL,
    )
    if not m:
        return None
    try:
        payload = json.loads(m.group(1))
    except (json.JSONDecodeError, TypeError):
        return None
    data = payload.get("data")
    shape = payload.get("shape")
    if data is None:
        return None
    return {"data": data, "shape": shape, "kind": payload.get("kind", "field")}


def _to_float_matrix(data: Any) -> tuple[list | None, list[int] | None]:
    """把 JSON 数据规范化为二维 float 列表（shape 优先按 data 推断）。"""
    if _np is not None:
        try:
            arr = _np.asarray(data, dtype=_np.float64)
        except Exception:  # noqa: BLE001
            return None, None
        if arr.size == 0:
            return None, None
        return arr.tolist(), list(arr.shape)
    # 纯 Python 降级
    try:
        if isinstance(data, (int, float)):
            return [[float(data)]], [1, 1]
        rows = []
        for row in data:
            if isinstance(row, (list, tuple)):
                rows.append([float(v) for v in row])
            else:
                rows.append([float(row)])
        if not rows:
            return None, None
        width = len(rows[0])
        for row in rows:
            if len(row) != width:
                return None, None
        return rows, [len(rows), width]
    except Exception:  # noqa: BLE001
        return None, None


def _compute_metrics(rows: list, shape: list[int]) -> dict:
    """计算物理量摘要（numpy 可用时用 numpy，否则纯 Python）。"""
    if _np is not None:
        arr = _np.asarray(rows, dtype=_np.float64)
        abs_arr = _np.abs(arr)
        max_p = float(abs_arr.max())
        rms_p = float(_np.sqrt(_np.mean(arr**2)))
        finite = bool(_np.all(_np.isfinite(arr)))
    else:
        vals = [v for row in rows for v in row]
        max_p = max(abs(v) for v in vals)
        rms_p = math.sqrt(sum(v * v for v in vals) / len(vals))
        finite = all(math.isfinite(v) for v in vals)
    has_signal = bool(finite and max_p > 0.0)
    return {
        "max_pressure": max_p,
        "rms_pressure": rms_p,
        "field_shape": list(shape),
        "has_signal": has_signal,
        "finite": finite,
    }


def _verdict(
    exit_code: int | None,
    timed_out: bool,
    metrics: dict,
) -> str:
    """按 VAL-1 口径判定结果状态。"""
    if exit_code not in (0, None) or timed_out:
        return "abnormal"  # 执行失败/超时
    if not metrics.get("finite", True):
        return "abnormal"  # NaN/Inf
    if metrics["max_pressure"] > _PHYSICAL_MAX_PRESSURE_PA:
        return "abnormal"  # 疑似数值发散
    if not metrics["has_signal"]:
        return "zero_field"  # 全零场（典型故障）
    return "normal"


def _heatmap_base64(rows: list, title: str = "Pressure field") -> str | None:
    """生成热力图 PNG → base64；无 matplotlib 时降级 ASCII 热力图。"""
    if _plt is None:
        return _ascii_heatmap(rows)
    try:
        arr = _np.asarray(rows, dtype=_np.float64) if _np is not None else _np  # type: ignore[assignment]
        if _np is None:
            return _ascii_heatmap(rows)
        vmax = float(_np.max(_np.abs(arr))) or 1.0
        fig, ax = _plt.subplots(figsize=(6, 5), dpi=80)
        im = ax.imshow(arr, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
        ax.set_title(title)
        ax.set_xlabel("x (grid)")
        ax.set_ylabel("y (grid)")
        fig.colorbar(im, ax=ax, label="Pressure (Pa)")
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        _plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:  # noqa: BLE001
        return _ascii_heatmap(rows)


def _waveform_base64(rows: list, title: str = "Pressure profile") -> str | None:
    """生成波形图 PNG → base64（2D 场取中心行剖面；1D 场直接画）。"""
    if _plt is None or _np is None:
        return None
    try:
        arr = _np.asarray(rows, dtype=_np.float64)
        if arr.ndim == 1:
            y = arr
        elif arr.ndim == 2 and arr.shape[0] > 1:
            y = arr[arr.shape[0] // 2, :]
        else:
            y = arr.ravel()
        fig, ax = _plt.subplots(figsize=(7, 3), dpi=80)
        ax.plot(y, lw=0.8)
        ax.set_title(title)
        ax.set_xlabel("index")
        ax.set_ylabel("Pressure (Pa)")
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        _plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:  # noqa: BLE001
        return None


def _ascii_heatmap(rows: list, width: int = 48) -> str | None:
    """ASCII 字符热力图降级（无 matplotlib 时）。"""
    try:
        vals = [[float(v) for v in row] for row in rows]
        if not vals:
            return None
        vmax = max(abs(v) for row in vals for v in row) or 1.0
        chars = " .:-=+*#%@"
        lines = []
        h = len(vals)
        step = max(1, h // 16)
        for i in range(0, h, step):
            row = vals[i]
            n = len(row)
            s = max(1, n // width)
            line = "".join(
                chars[min(9, int(abs(row[j]) / vmax * 9))]
                for j in range(0, n, s)
            )
            lines.append(line)
        return base64.b64encode(
            ("\n".join(lines) + f"\n# ASCII heatmap, vmax={vmax:.3g} Pa").encode("utf-8")
        ).decode("ascii")
    except Exception:  # noqa: BLE001
        return None


def _summary(metrics: dict, verdict: str) -> str:
    shape = "×".join(str(s) for s in metrics["field_shape"])
    parts = [
        f"峰值压力 {metrics['max_pressure']:.4g} Pa",
        f"RMS {metrics['rms_pressure']:.4g} Pa",
        f"网格 {shape}",
        f"verdict: {verdict}",
    ]
    if verdict == "zero_field":
        parts.append("（全场为零，常见原因：Sources 坐标浮点/整型错误、p0 误用为 Sources，见纠错速查表）")
    elif verdict == "abnormal":
        parts.append("（执行失败或数值异常，建议重试/检查参数）")
    return "，".join(parts)


def _analyze_impl(
    stdout_text: str,
    stderr_text: str = "",
    exit_code: int = 0,
    params_json: str = "{}",
) -> dict[str, Any]:
    """分析一次 jwave 仿真的输出：物理量摘要 + 热力图/波形图 + verdict。

    约定：仿真代码需将压力场以 JSON 打印在 stdout 的
    ``__ACOU_FIELD_START__ {json} __ACOU_FIELD_END__`` 标记之间
    （Dify 工作流代码生成 prompt 已注入该模板）。

    注：模块级独立实现，便于脱离 MCP 直接测试；register() 内注册同名工具，
    其函数体调用本函数（避免与工具名递归遮蔽）。
    """
    payload = _extract_field(stdout_text or "")
    rows, shape = _to_float_matrix(payload["data"]) if payload else (None, None)

    if rows is None:
        metrics = {
            "max_pressure": 0.0,
            "rms_pressure": 0.0,
            "field_shape": [],
            "has_signal": False,
            "finite": True,
        }
        verdict = _verdict(exit_code, False, metrics)
        if exit_code == 0 and verdict == "zero_field":
            verdict = "abnormal"  # 执行成功但未输出场数据 → 无法分析
        return {
            "has_signal": False,
            "max_pressure": 0.0,
            "rms_pressure": 0.0,
            "field_shape": [],
            "heatmap_png_base64": None,
            "waveform_png_base64": None,
            "verdict": verdict,
            "summary": f"未能从输出解析压力场（exit_code={exit_code}）。{_summary(metrics, verdict)}",
        }

    metrics = _compute_metrics(rows, shape)
    verdict = _verdict(exit_code, False, metrics)
    heatmap = _heatmap_base64(rows, title="Pressure field (max-abs over time)" if payload.get("kind") == "field" else "Pressure field")
    waveform = _waveform_base64(rows)

    return {
        "has_signal": metrics["has_signal"],
        "max_pressure": metrics["max_pressure"],
        "rms_pressure": metrics["rms_pressure"],
        "field_shape": metrics["field_shape"],
        "heatmap_png_base64": heatmap,
        "waveform_png_base64": waveform,
        "verdict": verdict,
        "summary": _summary(metrics, verdict),
    }


def register(mcp) -> None:
    """向 FastMCP 实例注册本模块工具。"""

    @mcp.tool
    def analyze_simulation_result(
        stdout_text: str,
        stderr_text: str = "",
        exit_code: int = 0,
        params_json: str = "{}",
    ) -> dict[str, Any]:
        """Analyze a jwave simulation output: physics summary + heatmap/waveform + verdict.

        Expects the simulation code to print the pressure field as JSON between
        ``__ACOU_FIELD_START__`` and ``__ACOU_FIELD_END__`` markers on stdout.
        Returns has_signal, max/rms pressure, field shape, heatmap/waveform PNG
        (base64) and a physical verdict (normal / zero_field / abnormal).
        """
        return _analyze_impl(
            stdout_text,
            stderr_text,
            exit_code,
            params_json,
        )
