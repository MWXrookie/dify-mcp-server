#!/usr/bin/env python3
"""T-012 · 20 次多轮仿真集成测试（阶段二收尾）

每个场景 = 初始完整需求 + 2 轮增量修改，走完整 /chat 链路
（DeepSeek 合并历史需求 → Dify 工作流执行 → 报告）。
判定：
  - 工作流 succeeded
  - 合并后 requirement 包含修改后的关键参数（上下文正确率）
输出 docs/test_report_phase2.md
"""
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = os.environ.get("GW_BASE_URL", "http://localhost:8001")
OUT = Path(__file__).resolve().parent / "docs" / "test_report_phase2.md"
RAW = Path(__file__).resolve().parent / "docs" / "test_results_multiturn_new.json"

# 每个场景: 初始需求 + [(增量修改, 期望合并后应包含的片段), ...]
SCENARIOS = [
    ("模拟一个2 MHz点声源在均匀介质中的声波传播，网格128x128，区域1cm x 1cm，模拟5微秒，声速1500 m/s",
     [("把频率改成3 MHz", "3 MHz")]),
    ("模拟2 MHz点声源在水中传播，网格160x160，区域1.2cm x 1.2cm，声速1500 m/s，仿真4微秒",
     [("把网格改成256x256", "256")]),
    ("中心点声源1.5 MHz，软组织声速1540 m/s，网格192x192，区域1cm，模拟5微秒",
     [("把区域改成1.5cm", "1.5")]),
    ("2 MHz点声源，声速1500 m/s，网格200x200，区域1cm，仿真4微秒",
     [("在距离中心2mm处放一个传感器记录压力波形", "传感器")]),
    ("1.8 MHz点声源在均匀介质中传播，网格180x180，区域1.2cm，声速1540 m/s，模拟5微秒",
     [("把声速改成1480 m/s", "1480")]),
    ("高斯初始压力脉冲，峰值1000 Pa，半宽0.5mm，网格256x256，区域1cm，声速1500 m/s",
     [("把峰值改成800 Pa", "800")]),
    ("2.2 MHz点声源，网格220x220，区域1.1cm，声速1500 m/s，模拟4.5微秒",
     [("把频率改成1 MHz", "1 MHz")]),
    ("环形初始压力，环半径1.5mm，峰值400 Pa，网格200x200，区域1.2cm，声速1540 m/s",
     [("把环半径改成2mm", "2mm")]),
    ("点声源2.5 MHz，区域0.8cm x 0.8cm，网格224x224，声速1500 m/s，仿真2.5微秒",
     [("把区域改成1cm", "1cm")]),
    ("点声源1.2 MHz，网格160x160，区域1.6cm，声速1520 m/s，模拟6微秒",
     [("把仿真时长改成3微秒", "3微秒")]),
    ("2 MHz点声源，水介质声速1500 m/s，网格192x192，区域1cm，仿真4微秒",
     [("改成异质介质：中心有直径2.5mm的低声速囊肿1420 m/s", "囊肿")]),
    ("椭圆初始压力，峰值900 Pa，长轴0.9mm短轴0.4mm，网格180x180，区域1cm，声速1480 m/s",
     [("把长轴改成1.2mm", "1.2")]),
    ("点声源3 MHz，网格224x224，区域0.8cm，声速1500 m/s，仿真2.5微秒",
     [("把频率改成2 MHz 且网格改成128x128", "2 MHz")]),
    ("点声源1.5 MHz，网格200x200，区域1.5cm，声速1540 m/s，模拟5微秒",
     [("把声速改成1600 m/s", "1600")]),
    ("双高斯初始压力，左右各一个，峰值500 Pa和700 Pa，网格192x192，区域1.5cm，声速1500 m/s",
     [("把两个峰值都改成600 Pa", "600")]),
    ("点声源2 MHz，网格160x160，区域1cm，声速1500 m/s，仿真3微秒",
     [("在上下左右各2mm放四个传感器", "传感器")]),
    ("点声源1 MHz，网格128x128，区域1cm，声速1500 m/s，模拟6微秒",
     [("把频率改成2.5 MHz", "2.5")]),
    ("高斯p0，峰值1200 Pa，半宽0.7mm，网格160x160，区域1.2cm，声速1540 m/s",
     [("把半宽改成1mm", "1mm")]),
    ("点声源2 MHz穿过双层介质，上层1480下层1650，网格200x200，区域1.5cm",
     [("把上层声速改成1500 m/s", "1500")]),
    ("点声源1.8 MHz，网格180x180，区域1.4cm，声速1540 m/s，模拟5微秒",
     [("把区域改成1.2cm 且仿真时长改成4微秒", "1.2")]),
]

TOTAL = len(SCENARIOS)
assert TOTAL == 20, f"Expected 20 scenarios, got {TOTAL}"


def chat(message: str, requirement: str = "") -> dict:
    body = json.dumps({"message": message, "requirement": requirement},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/chat", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read().decode("utf-8"))


def run_scenario(idx: int, initial: str, turns: list[tuple[str, str]]) -> dict:
    requirement = ""
    steps = []
    msgs = [initial] + [t[0] for t in turns]
    for t_i, msg in enumerate(msgs):
        t0 = time.time()
        try:
            d = chat(msg, requirement)
            elapsed = round(time.time() - t0, 1)
            ok = d.get("workflow_status") == "succeeded"
            requirement = d.get("requirement", "") or requirement
            steps.append({
                "turn": t_i + 1, "message": msg,
                "ok": ok, "elapsed": elapsed,
                "merge_used": d.get("merge_used"),
                "workflow_status": d.get("workflow_status"),
                "requirement": requirement,
                "report_head": (d.get("report", "") or "")[:100],
            })
        except Exception as e:
            elapsed = round(time.time() - t0, 1)
            steps.append({
                "turn": t_i + 1, "message": msg, "ok": False,
                "elapsed": elapsed, "error": str(e), "requirement": requirement,
            })
    # 上下文正确率：最后一轮合并后的 requirement 是否包含所有期望片段
    last_req = steps[-1].get("requirement", "") or ""
    checks = [{"expected": frag, "found": frag.lower() in last_req.lower()}
              for frag in [turns[0][1]]]
    context_ok = all(c["found"] for c in checks) and bool(last_req)
    workflow_ok = all(s.get("ok") for s in steps)
    return {
        "idx": idx,
        "initial": initial,
        "turns": turns,
        "steps": steps,
        "final_requirement": last_req,
        "context_ok": context_ok,
        "workflow_ok": workflow_ok,
        "success": context_ok and workflow_ok,
        "checks": checks,
    }


def main() -> int:
    print(f"T-012: {TOTAL} 个多轮场景，每个 = 初始需求 + {max(len(s[1]) for s in SCENARIOS)} 轮修改")
    print("=" * 80)
    results = []
    for i, (initial, turns) in enumerate(SCENARIOS, 1):
        sys.stdout.write(f"[{i:2d}/20] {initial[:40]}... ")
        sys.stdout.flush()
        r = run_scenario(i, initial, turns)
        results.append(r)
        if r["success"]:
            print(f"✅ ctx={r['context_ok']} wf={r['workflow_ok']} "
                  f"[{sum(s.get('elapsed', 0) for s in r['steps']):.0f}s]")
        else:
            print(f"❌ ctx={r['context_ok']} wf={r['workflow_ok']}")

    ok = [r for r in results if r["success"]]
    ctx_ok = [r for r in results if r["context_ok"]]
    wf_ok = [r for r in results if r["workflow_ok"]]
    ctx_rate = len(ctx_ok) / TOTAL * 100
    total_rate = len(ok) / TOTAL * 100

    RAW.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 阶段二 · T-012 多轮仿真集成测试报告",
        "",
        f"> 测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | 走 `/chat` 完整链路（合并→工作流→报告）",
        "",
        "## 总体结果",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
        f"| 场景数 | {TOTAL} |",
        f"| 上下文正确（合并后含修改参数） | {len(ctx_ok)}/{TOTAL} = **{ctx_rate:.1f}%** |",
        f"| 工作流成功 | {len(wf_ok)}/{TOTAL} = {len(wf_ok)/TOTAL*100:.1f}% |",
        f"| 全链路成功（上下文+工作流） | {len(ok)}/{TOTAL} = {total_rate:.1f}% |",
        f"| 门禁标准 | 上下文正确率 ≥ 85% |",
        f"| 门禁结果 | {'✅ 通过' if ctx_rate >= 85 else '❌ 未通过'} |",
        "",
        "## 场景明细",
        "",
        "| # | 初始需求(截断) | 修改轮 | 上下文 | 工作流 | 最终需求片段 |",
        "|---|---------------|--------|--------|--------|-------------|",
    ]
    for r in results:
        chk = "、".join(f"{c['expected']}:{'✓' if c['found'] else '✗'}" for c in r["checks"])
        lines.append(
            f"| {r['idx']} | {r['initial'][:36]}... | {len(r['turns'])} | "
            f"{'✅' if r['context_ok'] else '❌'} | {'✅' if r['workflow_ok'] else '❌'} | {chk} |"
        )
    lines += ["", "## 失败详情", ""]
    for r in results:
        if not r["success"]:
            lines.append(f"### #{r['idx']}")
            lines.append(f"- 初始: {r['initial']}")
            lines.append(f"- 修改: {r['turns']}")
            lines.append(f"- 最终需求: {r['final_requirement']}")
            for s in r["steps"]:
                if not s.get("ok"):
                    lines.append(f"- 第{s['turn']}轮失败: {s.get('error') or s.get('workflow_status')}")
            lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")

    print("=" * 80)
    print(f"上下文正确率: {len(ctx_ok)}/{TOTAL} = {ctx_rate:.1f}%  (门禁 ≥85%)")
    print(f"全链路成功: {len(ok)}/{TOTAL} = {total_rate:.1f}%")
    print(f"报告: {OUT}")
    return 0 if ctx_rate >= 85 else 1


if __name__ == "__main__":
    raise SystemExit(main())
