#!/usr/bin/env python
"""Apply the (mechanical, reviewable) API corrections to the jwave knowledge base.

The knowledge base shipped with the Dify app was written against an older /
slightly different jwave build.  Three patterns do not exist in the installed
``jwave 0.2.1`` and would make every generated script fail:

=====================================  ==========================================
wrong (in the KB)                      correct (jwave 0.2.1)
=====================================  ==========================================
``jw.np.array/np.abs/np.pi/...``       ``jnp.*`` (``import jax.numpy as jnp``)
``jw.show_field``                      ``jw.utils.show_field``
``jw.display_complex_field``           ``jw.utils.display_complex_field``
=====================================  ==========================================

Usage::

    python tools/fix_kb.py            # fix kb/jwave_kb_organized.md in place
    python tools/fix_kb.py --check    # only report, do not write
    python tools/fix_kb.py --revert    # restore from the .bak backup
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KB = PROJECT_ROOT / "kb" / "jwave_kb_organized.md"

FENCE_RE = re.compile(r"(?P<fence>```(?P<lang>[^\n`]*)\n)(?P<body>.*?)(?P<close>```)", re.S)

# (pattern, replacement, human description)
SUBSTITUTIONS: list[tuple[str, str, str]] = [
    (r"\bjw\.np\.", "jnp.", "jw.np.* -> jnp.*"),
    (r"\bjw\.show_field\b", "jw.utils.show_field", "jw.show_field -> jw.utils.show_field"),
    (
        r"\bjw\.display_complex_field\b",
        "jw.utils.display_complex_field",
        "jw.display_complex_field -> jw.utils.display_complex_field",
    ),
]

# Exact-string fixes verified by *actually executing* the corrected snippets
# against jwave 0.2.1 (see kb/FIXES.md).
EXACT_FIXES: list[tuple[str, str, str, int]] = [
    (
        "omega = 2 * jnp.pi * 1e6  # 1 MHz 角频率\n"
        "source = jw.TimeHarmonicSource(domain, [(64, 64)], [1.0], omega=omega)",
        "omega = 2 * jnp.pi * 1e6  # 1 MHz 角频率\n"
        "source = jw.TimeHarmonicSource.from_point_sources(\n"
        "    domain, x=[64], y=[64], value=[1.0], omega=omega\n"
        ")",
        "TimeHarmonicSource 使用示例 -> 通过 from_point_sources 构造",
        1,
    ),
    (
        "# 2. 定义时谐源 (1 MHz)\n"
        "omega = 2 * 3.14159 * 1e6\n"
        "source = jw.TimeHarmonicSource(domain, [(64, 64)], [1.0], omega=omega)",
        "# 2. 定义时谐源 (1 MHz) — helmholtz_solver 需要 OnGrid 源\n"
        "omega = 2 * jnp.pi * 1e6\n"
        "src_array = jnp.zeros(domain.N, dtype=jnp.complex64).at[64, 64].set(1.0)\n"
        "source = FourierSeries(src_array, domain)",
        "频域典型工作流 -> 改用 OnGrid(FourierSeries) 源",
        1,
    ),
    (
        "jw.utils.display_complex_field(field, title='Helmholtz solution')",
        "jw.utils.display_complex_field(field)",
        "display_complex_field 不支持 title 关键字（去掉）",
        2,
    ),
    (
        "**返回值**: 传感器在每个时间步的记录数据。",
        "**返回值**: 传感器在每个时间步的记录序列 `ys`。**默认未传 `sensors` 时记录的就是压力场 `p`**"
        "（源码里 `sensors = lambda p, u, rho: p`），所以 `result[-1]` 已经是最终压力场，"
        "**不需要**再调用 `pressure_from_density`；只有当你显式持有 PSTD 内部的密度场 `rho` 时才需要"
        "`pressure_from_density(rho, medium)` 做转换。",
        "simulate_wave_propagation 返回值说明（默认返回压力场，无需二次转换）",
        1,
    ),
    (
        "- `sample_freq`: 采样频率 [Hz]",
        "- `sample_freq`: 采样频率 [Hz]。**注意应传 `1/dt`，不是 `dt`**"
        "（例如 `tone_burst(1/time_axis.dt, 5e6, 3)`）",
        "tone_burst 第一参数语义澄清（1/dt 而非 dt）",
        1,
    ),
]

JNP_IMPORT_RE = re.compile(r"^\s*(?:import\s+jax\.numpy\s+as\s+jnp|from\s+jax\s+import\s+numpy\s+as\s+jnp)", re.M)
IMPORT_LINE_RE = re.compile(r"^[ \t]*(?:import|from)\s")
JNP_IMPORT = "import jax.numpy as jnp"


def _ensure_jnp_import(body: str) -> tuple[str, bool]:
    """Insert ``import jax.numpy as jnp`` when the block uses ``jnp`` but never imports it."""
    if "jnp." not in body or JNP_IMPORT_RE.search(body):
        return body, False
    lines = body.splitlines(keepends=True)
    last_import = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if IMPORT_LINE_RE.match(line):
            last_import = i
            continue
        break  # first "real" statement: stop scanning the header
    insert_at = last_import + 1
    newline = "" if insert_at >= len(lines) else ""
    lines.insert(insert_at, JNP_IMPORT + "\n")
    return "".join(lines) + newline, True


def fix_text(text: str) -> tuple[str, dict[str, int]]:
    report = {desc: len(re.findall(pat, text)) for pat, _rep, desc in SUBSTITUTIONS}
    for pat, rep, _desc in SUBSTITUTIONS:
        text = re.sub(pat, rep, text)

    for old, new, desc, expected in EXACT_FIXES:
        found = text.count(old)
        report[desc] = found
        if found == 0:          # already applied -> keep the tool idempotent
            continue
        if found != expected:
            print(f"  ! {desc}: expected {expected} match(es), found {found}", file=sys.stderr)
        text = text.replace(old, new)

    # ensure each fenced code block that now uses jnp can actually import it
    added = 0

    def _fix_fence(m: re.Match) -> str:
        nonlocal added
        lang, body = m.group("lang"), m.group("body")
        if lang.strip().lower() not in {"python", "py"}:
            return m.group(0)
        body, changed = _ensure_jnp_import(body)
        if changed:
            added += 1
        return f"{m.group('fence')}{body}{m.group('close')}"

    text = FENCE_RE.sub(_fix_fence, text)
    report["inserted `import jax.numpy as jnp` into code blocks"] = added
    return text, report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--kb", type=Path, default=DEFAULT_KB)
    p.add_argument("--out", type=Path, help="write elsewhere instead of in place")
    p.add_argument("--check", action="store_true", help="report only, do not write")
    p.add_argument("--revert", action="store_true", help="restore the .bak backup")
    args = p.parse_args(argv)

    kb: Path = args.kb
    backup = kb.with_suffix(kb.suffix + ".bak")

    if args.revert:
        if not backup.exists():
            print(f"error: no backup at {backup}", file=sys.stderr)
            return 2
        shutil.copyfile(backup, kb)
        print(f"restored {kb} from {backup}")
        return 0

    if not kb.exists():
        print(f"error: {kb} not found", file=sys.stderr)
        return 2

    original = kb.read_text(encoding="utf-8")
    fixed, report = fix_text(original)

    print(f"knowledge base: {kb}")
    for desc, count in report.items():
        print(f"  {count:3d} × {desc}")

    if args.check:
        print("(check only, nothing written)")
        return 0

    if not backup.exists():
        shutil.copyfile(kb, backup)
        print(f"  backup written -> {backup}")

    target = args.out or kb
    target.write_text(fixed, encoding="utf-8")
    print(f"  written -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
