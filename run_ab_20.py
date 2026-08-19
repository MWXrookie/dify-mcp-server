#!/usr/bin/env python3
"""A/B 提示词优化对比测试：同一批 20 题，优化前后各跑一次。

从 run_50_tests_new.PROMPTS 每类取前 4 题（5 类 × 4 = 20 题），
两次运行使用完全相同的题目与顺序，保证可比性。

用法:
  python3 run_ab_20.py baseline|optimized
结果: docs/test_report_ab20_{tag}.md + docs/test_results_ab20_{tag}.json
"""
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

import run_50_tests_new as r50

PER_CATEGORY = 4
PROMPTS = {
    cat: prompts[:PER_CATEGORY]
    for cat, prompts in r50.PROMPTS.items()
}
TOTAL = sum(len(v) for v in PROMPTS.values())
assert TOTAL == 20, f"Expected 20, got {TOTAL}"

OUT_DIR = Path(__file__).resolve().parent / "docs"


def run_one(idx: int, category: str, prompt: str) -> dict:
    start = time.time()
    body = json.dumps({
        "inputs": {"query": prompt},
        "response_mode": "blocking",
        "user": "ab20",
    }).encode()
    req = urllib.request.Request(r50.API, data=body, headers=r50.HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode()
        elapsed = time.time() - start
        data = json.loads(raw)
        wf = data.get("data", {})
        outputs = wf.get("outputs", {}).get("text", [])
        if isinstance(outputs, str):
            o = {"stdout": outputs, "stderr": "", "exit_code": 0 if wf.get("status") == "succeeded" else 1,
                 "timed_out": False, "duration_ms": None, "total_attempts": 1}
        else:
            o = outputs[0] if isinstance(outputs, list) and outputs else (outputs if isinstance(outputs, dict) else {})

        result = {
            "idx": idx, "category": category, "prompt": prompt,
            "elapsed": elapsed, "workflow_status": wf.get("status"),
            "workflow_error": wf.get("error"),
        }
        if isinstance(o, dict) and o:
            stdout = o.get("stdout", "") or ""
            stderr = o.get("stderr", "") or ""
            result.update({
                "exit_code": o.get("exit_code"), "timed_out": o.get("timed_out"),
                "duration_ms": o.get("duration_ms"), "stdout": stdout, "stderr": stderr,
                "total_attempts": o.get("total_attempts"), "has_image": bool(o.get("image_base64")),
            })
            max_pressure = None
            for pattern in (r"最大压[力强].*?([\d.eE+-]+)",
                            r"max(?:imum)?\s+pressure\s*[:=]\s*([\d.eE+-]+)",
                            r"max_p\s*[:=]\s*([\d.eE+-]+)"):
                m = re.search(pattern, stdout, re.IGNORECASE | re.S)
                if m:
                    try:
                        max_pressure = float(m.group(1))
                    except ValueError:
                        pass
                    break
            result["max_pressure"] = max_pressure
            status_ok = wf.get("status") == "succeeded" or result.get("exit_code") == 0
            result["success"] = bool(
                status_ok and not result.get("timed_out")
                and max_pressure is not None and max_pressure > 0
            )
        else:
            result["success"] = False
            result["raw_output_missing"] = True
        return result
    except Exception as exc:
        return {"idx": idx, "category": category, "prompt": prompt,
                "elapsed": time.time() - start, "error": str(exc), "success": False}


def fail_reason(r: dict) -> str:
    if r.get("error"): return r["error"][:100]
    if r.get("workflow_error"): return str(r["workflow_error"])[:100]
    if r.get("timed_out"): return "超时"
    if r.get("workflow_status") not in (None, "succeeded", "running"):
        return f"wf={r.get('workflow_status')}"
    if r.get("exit_code") not in (None, 0):
        return f"exit={r.get('exit_code')}"
    if r.get("max_pressure") == 0: return "全零"
    if r.get("raw_output_missing"): return "输出缺失"
    return "未知"


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else "run"
    print(f"A/B 20题: tag={tag} | {TOTAL} 题 (5类×4)")
    print("=" * 80)
    results = []
    for i, (cat, prompt) in enumerate(
        ((c, p) for c in PROMPTS for p in PROMPTS[c]), 1):
        sys.stdout.write(f"[{i:2d}/20] {cat}: {prompt[:40]}... ")
        sys.stdout.flush()
        r = run_one(i, cat, prompt)
        results.append(r)
        if r["success"]:
            print(f"✅ max_p={r.get('max_pressure'):.4f}"
                  + (f" retry×{r.get('total_attempts')}" if (r.get('total_attempts') or 1) > 1 else ""))
        else:
            print(f"❌ {fail_reason(r)[:80]}")

    ok = [r for r in results if r["success"]]
    rate = len(ok) / TOTAL * 100

    (OUT_DIR / f"test_results_ab20_{tag}.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# A/B 20 题对比测试报告 — {tag}",
        "",
        f"> 测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | 固定 20 题（5 类×4）走 Dify 工作流",
        "",
        "## 总体结果",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| 总题数 | {TOTAL} |",
        f"| 成功 | {len(ok)} |",
        f"| 失败 | {TOTAL - len(ok)} |",
        f"| **成功率** | **{rate:.1f}%** |",
        "",
        "## 按类别",
        "",
        "| 类别 | 成功/总数 | 成功率 |",
        "|------|-----------|--------|",
    ]
    for cat in PROMPTS:
        cr = [r for r in results if r["category"] == cat]
        co = [r for r in cr if r["success"]]
        lines.append(f"| {cat} | {len(co)}/{len(cr)} | {len(co)/len(cr)*100:.0f}% |")
    lines += ["", "## 明细", "", "| # | 类别 | 结果 | 备注 |", "|---|------|------|------|"]
    for r in results:
        lines.append(f"| {r['idx']} | {r['category']} | {'✅' if r['success'] else '❌'} | "
                     + (f"max_p={r['max_pressure']:.4f}" if r.get('max_pressure') is not None else fail_reason(r)) + " |")
    (OUT_DIR / f"test_report_ab20_{tag}.md").write_text("\n".join(lines), encoding="utf-8")

    print("=" * 80)
    print(f"{tag}: {len(ok)}/{TOTAL} = {rate:.1f}%")
    print(f"报告: docs/test_report_ab20_{tag}.md")
    return 0 if rate >= 85 else 1


if __name__ == "__main__":
    raise SystemExit(main())
