#!/usr/bin/env python3
"""A/B 难题集 20 题：重点覆盖代码骨架的防御价值场景。

场景设计（比 run_ab_20 更难，突出传感器/异质/环形/3D/组合）：
- 传感器精确取值（6题）：多传感器阵列、圆周、近场、传感器+异质组合
- 异质介质构造（5题）：多囊肿、分层、声速渐变、源在异质旁
- p0 环形/椭圆（3题）：环形+传感器、双环
- 3D（3题）：3D 点源、3D p0、3D 内存约束
- 组合/边界（3题）：异质+传感器、环形半径边界、p0+传感器

用法: python3 run_ab_20_hard.py baseline|optimized
"""
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

API = "http://localhost/v1/workflows/run"
TOKEN = os.environ.get("DIFY_API_KEY", "")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
OUT_DIR = Path(__file__).resolve().parent / "docs"

PROMPTS = {
    "传感器阵列": [
        "模拟中心2 MHz点声源传播，在距离中心1mm、2mm、3mm处沿+x轴放置3个传感器，记录各传感器峰值压力并比较，声速1500 m/s，网格192x192，区域1cm，仿真4微秒",
        "均匀软组织1.5 MHz点源，在半径2mm圆周上均匀放置6个传感器，记录各传感器峰值压力并输出最大值所在角度，声速1540 m/s，网格200x200，区域1.2cm",
        "2 MHz点源，x轴正方向每0.8mm放5个传感器组成线阵，输出各传感器到达时间（压力首次超过最大压力10%的时刻），声速1480 m/s，网格160x160，区域1cm，仿真6微秒",
        "四角传感器检测中心点源：2.5 MHz，四个角各一个传感器，比较四角峰值压力是否一致并解释，声速1500 m/s，网格192x192，区域1cm，模拟3微秒",
        "点源2 MHz，传感器距离声源0.5mm、1mm、1.5mm三个近场位置，记录波形并比较峰值，声速1500 m/s，网格160x160，区域0.8cm，仿真3微秒",
        "中心2 MHz点源，在上下左右各2mm放置4个传感器，输出四路波形并找出峰值压力最大的一路，声速1500 m/s，网格200x200，区域1cm，模拟4微秒",
    ],
    "异质介质构造": [
        "点源1.8 MHz穿过低声速圆形囊肿：背景1540 m/s，囊肿直径2.5mm声速1420 m/s，源在左侧中心，另在囊肿前后各放一个传感器比较波形差异，网格220x220，区域1.5cm，仿真5微秒",
        "中心3mm直径高声速包块1800 m/s，背景1500 m/s，点源2 MHz位于包块下方2mm，在包块上下各放传感器对比透射与绕射，网格192x192，区域1.2cm",
        "两层组织：上层1480 m/s下层1650 m/s，点源1.5 MHz在上层中央，在界面两侧各放传感器记录透射/反射波，网格200x200，区域1.5cm，模拟5微秒",
        "椭圆脂肪样低声速区（长轴4mm短轴2mm，1400 m/s，背景1540 m/s），点源2 MHz在中心左侧，在椭圆焦点附近放传感器，网格200x200，区域1.6cm",
        "声速从1450渐变到1600 m/s的圆形渐变区，背景1540 m/s，点源1.8 MHz左侧，在渐变区前后放传感器对比波形，网格200x200，区域1.4cm，仿真5微秒",
    ],
    "p0环形椭圆": [
        "环形初始压力：环半径1.5mm峰值400 Pa，在环中心与环外2mm各放传感器记录到达波形，声速1540 m/s，网格200x200，区域1.2cm，模拟4微秒",
        "双同心环初始压力：内环1mm外环2.5mm，峰值500 Pa，输出两环各自传播的波峰，声速1500 m/s，网格220x220，区域1.5cm，仿真5微秒",
        "椭圆初始压力：长轴1.2mm短轴0.6mm峰值900 Pa，在长轴方向与短轴方向各放传感器比较波前到达差异，声速1480 m/s，网格180x180，区域1cm，仿真4微秒",
    ],
    "3D仿真": [
        "3D球面波：中心300 kHz点源，计算域48x48x48网格dx0.5mm，声速1500 m/s，沿+x轴在8mm和12mm放探针比较1/r衰减，仿真20微秒",
        "3D高斯球初始压力：峰值1 Pa半宽1mm，48立方网格dx0.5mm，声速1500 m/s，输出最大压力与传播半径，仿真20微秒",
        "3D点源低频传播：200 kHz，56立方网格dx0.5mm（内存有限注意N≤72），声速1500 m/s，报告最大压力，仿真25微秒",
    ],
    "组合边界": [
        "点源2 MHz穿过含两个囊肿的异质介质（直径1.5mm和2mm，1450 m/s，背景1540 m/s），在囊肿后方放传感器记录透射波形，网格256x256，区域1.8cm",
        "环形初始压力半径2mm恰好接近物理区边界（网格200 dx0.1mm pml20），验证是否有信号并报告最大压力，声速1500 m/s，仿真4微秒",
        "双高斯p0左右各一个（峰值500和700 Pa，间距2mm），在两源连线中点放传感器记录合成波形，网格192x192，区域1.5cm，声速1500 m/s，仿真5微秒",
    ],
}
TOTAL = sum(len(v) for v in PROMPTS.values())
assert TOTAL == 20, f"Expected 20, got {TOTAL}"


def run_one(idx: int, category: str, prompt: str) -> dict:
    start = time.time()
    body = json.dumps({"inputs": {"query": prompt}, "response_mode": "blocking", "user": "ab20hard"}).encode()
    req = urllib.request.Request(API, data=body, headers=HEADERS)
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
        result = {"idx": idx, "category": category, "prompt": prompt, "elapsed": elapsed,
                  "workflow_status": wf.get("status"), "workflow_error": wf.get("error")}
        if isinstance(o, dict) and o:
            stdout = o.get("stdout", "") or ""
            result.update({"exit_code": o.get("exit_code"), "timed_out": o.get("timed_out"),
                           "duration_ms": o.get("duration_ms"), "stdout": stdout,
                           "stderr": o.get("stderr", "") or "",
                           "total_attempts": o.get("total_attempts")})
            max_pressure = None
            for pattern in (r"最大压[力强].*?([\d.eE+-]+)", r"max(?:imum)?\s+pressure\s*[:=]\s*([\d.eE+-]+)",
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
            result["success"] = bool(status_ok and not result.get("timed_out")
                                     and max_pressure is not None and max_pressure > 0)
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
    print(f"A/B 难题 20题: tag={tag}")
    print("=" * 80)
    results = []
    for i, (cat, prompt) in enumerate(((c, p) for c in PROMPTS for p in PROMPTS[c]), 1):
        sys.stdout.write(f"[{i:2d}/20] {cat}: {prompt[:38]}... ")
        sys.stdout.flush()
        r = run_one(i, cat, prompt)
        results.append(r)
        print(f"✅ max_p={r.get('max_pressure'):.4f}" if r["success"]
              else f"❌ {fail_reason(r)[:90]}")

    ok = [r for r in results if r["success"]]
    rate = len(ok) / TOTAL * 100
    (OUT_DIR / f"test_results_ab20hard_{tag}.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# A/B 难题 20 题对比测试报告 — {tag}", "",
        f"> 测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | 20 难题走 Dify 工作流", "",
        "## 总体结果", "", "| 指标 | 值 |", "|------|-----|",
        f"| 总题数 | {TOTAL} |", f"| 成功 | {len(ok)} |",
        f"| 失败 | {TOTAL - len(ok)} |", f"| **成功率** | **{rate:.1f}%** |", "",
        "## 按类别", "", "| 类别 | 成功/总数 | 成功率 |", "|------|-----------|--------|",
    ]
    for cat in PROMPTS:
        cr = [r for r in results if r["category"] == cat]
        co = [r for r in cr if r["success"]]
        lines.append(f"| {cat} | {len(co)}/{len(cr)} | {len(co)/len(cr)*100:.0f}% |")
    lines += ["", "## 明细", "", "| # | 类别 | 结果 | 备注 |", "|---|------|------|------|"]
    for r in results:
        lines.append(f"| {r['idx']} | {r['category']} | {'✅' if r['success'] else '❌'} | "
                     + (f"max_p={r['max_pressure']:.4f}" if r.get('max_pressure') is not None else fail_reason(r)) + " |")
    (OUT_DIR / f"test_report_ab20hard_{tag}.md").write_text("\n".join(lines), encoding="utf-8")

    print("=" * 80)
    print(f"{tag}: {len(ok)}/{TOTAL} = {rate:.1f}%")
    print(f"报告: docs/test_report_ab20hard_{tag}.md")
    return 0 if rate >= 85 else 1


if __name__ == "__main__":
    raise SystemExit(main())
