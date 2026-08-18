#!/usr/bin/env python3
"""T-006 retest with a fresh set of 50 natural-language acoustic prompts.

All cases go through the Dify workflow API, not direct MCP/tool calls.
"""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

API = "http://localhost/v1/workflows/run"
import os
TOKEN = os.environ.get("DIFY_API_KEY", "")
GW_BASE = os.environ.get("GW_BASE_URL", "http://localhost:8001")  # 网关地址可配
CACHE_API = f"{GW_BASE}/dashboard/api/cache_stats"
OUTPUT = Path(__file__).resolve().parent / "docs" / "test_report_phase1_new.md"
RAW_OUTPUT = Path(__file__).resolve().parent / "docs" / "test_results_raw_new.json"

PROMPTS = {
    "2D均质点源": [
        "在均匀水介质中模拟1.2 MHz点声源从计算域中心向外传播，声速1500 m/s，密度1000 kg/m^3，网格160x160，区域1.2cm x 1.2cm，仿真4微秒，并报告最大压力。",
        "做一个软组织中点声源传播仿真：声源频率2.4 MHz，声速1540 m/s，网格192x192，区域1cm见方，声源在中心，模拟3.5微秒。",
        "二维均匀介质声波传播：中心点声源频率800 kHz，声速1480 m/s，网格128x128，区域2cm x 2cm，模拟10微秒。",
        "请仿真一个3 MHz点声源在水中传播，计算区域0.8cm x 0.8cm，网格224x224，声速1500 m/s，仿真2.5微秒，输出最大压力。",
        "在1.5cm正方形区域中放置一个中心点声源，频率1.6 MHz，介质均匀声速1520 m/s，网格180x180，模拟5微秒。",
        "模拟一个2.8 MHz的超声点源在均匀软组织中传播，声速1540 m/s，密度1050 kg/m^3，网格256x256，区域1.2cm，仿真4微秒。",
        "均匀介质声场测试：点声源位于区域中心，频率1 MHz，声速1500 m/s，网格96x96，区域1cm x 1cm，仿真6微秒。",
        "请生成中心点声源的二维传播结果：频率2 MHz，声速1490 m/s，网格220x220，区域1.1cm见方，模拟4.5微秒。",
        "水中点源仿真，频率1.75 MHz，区域1.4cm x 1.4cm，网格200x200，声速1500 m/s，仿真时间5.5微秒。",
        "做一个快速基准仿真：均匀介质，中心点声源2.2 MHz，网格144x144，区域1cm x 1cm，声速1540 m/s，模拟3微秒。",
    ],
    "2D均质初始压力": [
        "模拟圆形高斯初始压力p0在均匀水介质中的传播，峰值800 Pa，标准宽度0.4mm，网格192x192，区域1cm x 1cm，声速1500 m/s，仿真4微秒。",
        "用初始压力场作为声源：中心高斯压力峰值1200 Pa，半宽0.7mm，软组织声速1540 m/s，网格160x160，区域1.2cm，模拟5微秒。",
        "仿真一个偏离中心1mm的高斯p0初始压力脉冲，峰值600 Pa，半宽0.5mm，均匀介质声速1500 m/s，网格200x200，区域1cm，模拟3微秒。",
        "二维p0声波传播：两个圆形高斯初始压力分别位于左右两侧，峰值500 Pa和700 Pa，半宽0.6mm，网格192x192，区域1.5cm，声速1500 m/s。",
        "请模拟初始压力分布传播，p0为中心椭圆高斯，峰值900 Pa，长轴0.9mm短轴0.4mm，声速1480 m/s，网格180x180，区域1cm，仿真4微秒。",
        "均匀介质中初始压力环形分布传播：环半径1.5mm，峰值400 Pa，声速1540 m/s，网格200x200，区域1.2cm，模拟4微秒。",
        "模拟一个较弱的高斯初始压力脉冲，峰值250 Pa，半宽1mm，声速1500 m/s，密度1000 kg/m^3，网格128x128，区域1cm，仿真3微秒。",
        "p0初始条件测试：中心高斯峰值1500 Pa，半宽0.35mm，均匀介质声速1520 m/s，网格224x224，区域0.9cm，模拟3.5微秒。",
        "请仿真三个位于同一直线上的高斯初始压力点，峰值均为300 Pa，间距1mm，声速1500 m/s，网格192x192，区域1.2cm，仿真4微秒。",
        "模拟初始压力由一个宽高斯包络构成的声波传播，峰值1000 Pa，半宽1.2mm，网格160x160，区域1.6cm，声速1540 m/s，模拟6微秒。",
    ],
    "2D异质介质": [
        "模拟点声源穿过一个低声速圆形囊肿：背景声速1540 m/s，囊肿直径2.5mm且声速1420 m/s，点声源1.8 MHz在左侧中心，网格220x220，区域1.5cm，仿真5微秒。",
        "异质介质仿真：中心有一个3mm直径高声速包块，声速1800 m/s，背景1500 m/s，点声源2 MHz位于包块下方2mm，网格192x192，区域1.2cm。",
        "模拟声波经过上下两层组织，上层声速1480 m/s，下层声速1650 m/s，点声源1.5 MHz位于上层中央，网格200x200，区域1.5cm，模拟5微秒。",
        "组织中有两个低声速囊肿，直径分别1.5mm和2mm，声速1450 m/s，背景1540 m/s，中心点源2 MHz，网格256x256，区域1.8cm。",
        "骨样区域散射仿真：右侧有一个矩形高声速区域2800 m/s，背景软组织1540 m/s，左侧点源1.2 MHz，网格224x224，区域2cm，仿真6微秒。",
        "模拟一个椭圆形脂肪样低声速区域，长轴4mm短轴2mm，声速1400 m/s，背景1540 m/s，点源2 MHz在中心左侧，网格200x200，区域1.6cm。",
        "随机斑点异质介质：背景声速1500 m/s，叠加小幅空间扰动约±3%，中心点声源1.5 MHz，网格180x180，区域1cm，模拟4微秒。",
        "模拟声波从水进入软组织界面：左半区1500 m/s，右半区1540 m/s，点声源2.5 MHz在左半区，网格192x192，区域1cm，仿真3微秒。",
        "含有三个小圆形高声速散射体的介质，散射体声速1700 m/s，背景1500 m/s，点声源2 MHz，网格220x220，区域1.5cm，模拟5微秒。",
        "在中心圆形区域内声速逐渐从1450过渡到1600 m/s，背景1540 m/s，点声源1.8 MHz在左侧，网格200x200，区域1.4cm，仿真5微秒。",
    ],
    "传感器记录": [
        "模拟中心2 MHz点声源传播，并在右侧1mm、2mm、3mm三个位置放置传感器记录压力波形，声速1500 m/s，网格192x192，区域1cm，仿真4微秒。",
        "在均匀软组织中做传感器阵列仿真：中心1.5 MHz点声源，四个传感器位于上下左右各2mm，声速1540 m/s，网格200x200，区域1.2cm，模拟5微秒。",
        "模拟一个2.2 MHz点声源，并在半径2.5mm圆周上放置6个传感器，记录各传感器峰值压力，网格224x224，区域1.4cm，声速1500 m/s。",
        "线阵接收测试：点源频率1 MHz，在x轴正方向每隔0.8mm放置5个传感器，声速1480 m/s，网格160x160，区域1cm，仿真6微秒。",
        "请仿真四角传感器检测中心点源，点源频率2.5 MHz，声速1500 m/s，网格192x192，区域1cm x 1cm，模拟3微秒，并输出到达时间。",
        "传感器记录p0传播：中心高斯初始压力峰值700 Pa，半宽0.6mm，在距离中心2mm处放置两个传感器，网格180x180，区域1.2cm，声速1540 m/s。",
        "模拟点声源在含低声速囊肿介质中的传播，并在囊肿前后各放一个传感器比较波形，点源1.8 MHz，网格200x200，区域1.5cm。",
        "8通道接收阵列测试：中心2 MHz点声源，8个传感器沿一条水平线均匀分布，声速1500 m/s，网格224x224，区域1.2cm，仿真4微秒。",
        "在区域左侧放置1.5 MHz点源，右侧竖直方向放置5个传感器形成线阵，均匀介质声速1540 m/s，网格200x200，区域1.5cm。",
        "模拟近场传感器：点源2 MHz，传感器距离声源0.5mm、1mm、1.5mm，声速1500 m/s，网格160x160，区域0.8cm，仿真3微秒。",
    ],
    "边界情况": [
        "低频大波长测试：200 kHz点声源在5cm x 5cm区域中传播，声速1500 m/s，网格160x160，模拟25微秒。",
        "小网格快速测试：64x64网格，区域8mm x 8mm，中心1 MHz点声源，声速1500 m/s，仿真2微秒。",
        "短时传播测试：2 MHz点声源，网格200x200，区域1cm，声速1500 m/s，只模拟0.8微秒。",
        "长时间传播测试：800 kHz点声源，区域2cm x 2cm，网格160x160，声速1540 m/s，模拟12微秒。",
        "高频分辨率挑战：4 MHz点声源，区域1cm x 1cm，网格256x256，声速1500 m/s，仿真3微秒，检查是否满足采样要求。",
        "超小区域测试：区域3mm x 3mm，网格192x192，中心3 MHz点声源，声速1500 m/s，模拟1.5微秒。",
        "靠近边界的点声源：点源距离左边界0.8mm，频率1.5 MHz，网格200x200，区域1cm，声速1500 m/s，模拟4微秒。",
        "大区域中等网格：区域4cm x 4cm，网格192x192，点源频率700 kHz，声速1500 m/s，模拟18微秒。",
        "故意设置较粗网格：点源频率3 MHz，网格80x80，区域1cm x 1cm，声速1500 m/s，模拟3微秒，观察参数校验是否提示风险。",
        "高声速介质边界测试：均匀介质声速2200 m/s，点源1.5 MHz，网格200x200，区域1.5cm，模拟5微秒。",
    ],
}

TOTAL = sum(len(v) for v in PROMPTS.values())
assert TOTAL == 50, f"Expected 50 prompts, got {TOTAL}"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}


def fetch_cache() -> dict:
    try:
        with urllib.request.urlopen(CACHE_API, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        return {"error": str(exc)}


def run_one(idx: int, category: str, prompt: str) -> dict:
    start = time.time()
    body = json.dumps({
        "inputs": {"query": prompt},
        "response_mode": "blocking",
        "user": "t006-new",
    }).encode()
    req = urllib.request.Request(API, data=body, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode()
        elapsed = time.time() - start
        data = json.loads(raw)
        wf = data.get("data", {})
        outputs = wf.get("outputs", {}).get("text", [])
        o = outputs[0] if isinstance(outputs, list) and outputs else (outputs if isinstance(outputs, dict) else {})

        result = {
            "idx": idx,
            "category": category,
            "prompt": prompt,
            "elapsed": elapsed,
            "workflow_status": wf.get("status"),
            "workflow_error": wf.get("error"),
        }
        if isinstance(o, dict) and o:
            stdout = o.get("stdout", "") or ""
            stderr = o.get("stderr", "") or ""
            result.update({
                "exit_code": o.get("exit_code"),
                "timed_out": o.get("timed_out"),
                "duration_ms": o.get("duration_ms"),
                "stdout": stdout,
                "stderr": stderr,
                "total_attempts": o.get("total_attempts"),
                "has_image": bool(o.get("image_base64")),
            })
            max_pressure = None
            for pattern in (
                r"最大压[力强].*?([\d.eE+-]+)",
                r"max(?:imum)?\s+pressure\s*[:=]\s*([\d.eE+-]+)",
                r"max_p\s*[:=]\s*([\d.eE+-]+)",
            ):
                m = re.search(pattern, stdout, re.IGNORECASE | re.S)
                if m:
                    try:
                        max_pressure = float(m.group(1))
                    except ValueError:
                        pass
                    break
            result["max_pressure"] = max_pressure
            result["success"] = bool(
                result.get("exit_code") == 0
                and not result.get("timed_out")
                and (max_pressure is None or max_pressure > 0)
            )
        else:
            result["success"] = False
            result["raw_output_missing"] = True
        return result
    except Exception as exc:
        elapsed = time.time() - start
        return {
            "idx": idx,
            "category": category,
            "prompt": prompt,
            "elapsed": elapsed,
            "error": str(exc),
            "success": False,
        }


def summarize_failure(result: dict) -> str:
    if result.get("error"):
        return result["error"]
    if result.get("workflow_error"):
        return result["workflow_error"]
    if result.get("timed_out"):
        return "timed_out"
    if result.get("exit_code") not in (None, 0):
        stderr = (result.get("stderr") or "").strip().splitlines()
        return stderr[-1][:120] if stderr else f"exit={result.get('exit_code')}"
    if result.get("max_pressure") == 0:
        return "ZERO_PRESSURE"
    if result.get("raw_output_missing"):
        return "workflow output missing"
    return "unknown"


def generate_report(results: list[dict], before_cache: dict, after_cache: dict) -> None:
    success = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    rate = len(success) / len(results) * 100
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    lines.append("# 阶段一 · T-006 新题 50 次端到端回归测试报告")
    lines.append("")
    lines.append(f"> 测试时间: {now} | 输入方式: Dify 工作流自然语言声学问题")
    lines.append("")
    lines.append("## 总体结果")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("|------|-----|")
    lines.append(f"| 总测试数 | {len(results)} |")
    lines.append(f"| 成功 | {len(success)} |")
    lines.append(f"| 失败 | {len(failed)} |")
    lines.append(f"| **成功率** | **{rate:.1f}%** |")
    lines.append("| 门禁标准 | ≥ 90% |")
    lines.append(f"| 门禁结果 | {'✅ 通过' if rate >= 90 else '❌ 未通过'} |")
    lines.append("")

    lines.append("## 按类别统计")
    lines.append("")
    lines.append("| 类别 | 成功/总数 | 成功率 | 平均耗时 | 平均重试次数 |")
    lines.append("|------|-----------|--------|----------|-------------|")
    for cat in PROMPTS:
        cat_results = [r for r in results if r["category"] == cat]
        cat_ok = [r for r in cat_results if r.get("success")]
        avg_dur = sum((r.get("duration_ms") or 0) for r in cat_results) / len(cat_results)
        avg_retry = sum((r.get("total_attempts") or 0) for r in cat_results) / len(cat_results)
        lines.append(f"| {cat} | {len(cat_ok)}/{len(cat_results)} | {len(cat_ok)/len(cat_results)*100:.0f}% | {avg_dur:.0f} ms | {avg_retry:.2f} |")
    lines.append("")

    lines.append("## 全部测试明细")
    lines.append("")
    lines.append("| # | 类别 | Prompt (截断) | 结果 | 最大压力 | 耗时 | 重试 | 备注 |")
    lines.append("|---|------|-------------|------|---------|------|------|------|")
    for r in results:
        flag = "✅" if r.get("success") else "❌"
        mp = f"{r['max_pressure']:.4f}" if isinstance(r.get("max_pressure"), (int, float)) else "N/A"
        dur = f"{r['duration_ms']:.0f}ms" if r.get("duration_ms") else f"{r.get('elapsed', 0):.1f}s"
        retry = r.get("total_attempts", "-")
        note = "" if r.get("success") else summarize_failure(r).replace("|", "/")[:80]
        lines.append(f"| {r['idx']} | {r['category']} | {r['prompt'][:42]}... | {flag} | {mp} | {dur} | {retry} | {note} |")
    lines.append("")

    if failed:
        lines.append("## 失败分析")
        lines.append("")
        for r in failed:
            lines.append(f"### #{r['idx']} {r['category']}")
            lines.append("")
            lines.append(f"- **Prompt**: {r['prompt']}")
            lines.append(f"- **Workflow Status**: {r.get('workflow_status', 'N/A')}")
            lines.append(f"- **Exit Code**: {r.get('exit_code', 'N/A')}")
            lines.append(f"- **Reason**: {summarize_failure(r)}")
            lines.append(f"- **Stdout**: {(r.get('stdout') or 'N/A')[:500]}")
            lines.append(f"- **Stderr**: {(r.get('stderr') or 'N/A')[:500]}")
            lines.append("")

    lines.append("## 纠错经验缓存前后")
    lines.append("")
    lines.append(f"- 测试前: `{json.dumps(before_cache, ensure_ascii=False)}`")
    lines.append(f"- 测试后: `{json.dumps(after_cache, ensure_ascii=False)}`")
    lines.append("")

    OUTPUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    all_prompts = []
    for category, prompts in PROMPTS.items():
        all_prompts.extend((category, prompt) for prompt in prompts)

    before_cache = fetch_cache()
    results = []

    print(f"共 {len(all_prompts)} 个新测试用例，全部通过 Dify 工作流 API 执行")
    print("=" * 80)
    for i, (category, prompt) in enumerate(all_prompts, start=1):
        sys.stdout.write(f"[{i:2d}/50] {category}: {prompt[:54]}... ")
        sys.stdout.flush()
        result = run_one(i, category, prompt)
        results.append(result)
        if result.get("success"):
            mp = result.get("max_pressure")
            attempts = result.get("total_attempts") or 1
            dur = result.get("duration_ms")
            msg = "✅"
            if mp is not None:
                msg += f" max_p={mp:.4f}"
            if attempts and attempts > 1:
                msg += f" retry×{attempts}"
            if dur:
                msg += f" [{dur:.0f}ms]"
            else:
                msg += f" [{result.get('elapsed', 0):.1f}s]"
            print(msg)
        else:
            print(f"❌ {summarize_failure(result)[:100]}")

    after_cache = fetch_cache()
    RAW_OUTPUT.write_text(json.dumps({
        "before_cache": before_cache,
        "after_cache": after_cache,
        "results": results,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    generate_report(results, before_cache, after_cache)

    success_count = sum(1 for r in results if r.get("success"))
    rate = success_count / len(results) * 100
    print("\n" + "=" * 80)
    print(f"总计: {len(results)} 次")
    print(f"成功: {success_count} 次")
    print(f"失败: {len(results) - success_count} 次")
    print(f"成功率: {rate:.1f}%")
    print(f"报告已保存: {OUTPUT}")
    print(f"原始数据已保存: {RAW_OUTPUT}")
    print("缓存前:", json.dumps(before_cache, ensure_ascii=False))
    print("缓存后:", json.dumps(after_cache, ensure_ascii=False))
    return 0 if rate >= 90 else 1


if __name__ == "__main__":
    raise SystemExit(main())
