"""代码执行链路：代码清理（防护注入）、沙箱提交、Markdown 报告生成。"""

import re
from typing import Any

import httpx

import config


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
        f"{config.EXECUTOR_URL}/execute",
        headers={"X-Executor-Token": config.EXECUTOR_SHARED_TOKEN},
        json={"code": code, "timeout_seconds": timeout_seconds},
        timeout=timeout_seconds + 10,
    )
    response.raise_for_status()
    return response.json()


def _build_report(result: dict[str, Any], original_code: str) -> str:
    """Build a human-readable Markdown report from execution results."""
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
