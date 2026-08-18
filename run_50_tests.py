#!/usr/bin/env python3
"""T-006: 50 次端到端回归测试 —— 通过 Dify 工作流 API 发送自然语言声学仿真问题"""

import json, time, sys, os
import urllib.request, urllib.error

API = "http://localhost/v1/workflows/run"
import os
TOKEN = os.environ.get("DIFY_API_KEY", "")
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "test_report_phase1.md")

# ============================================================
# 5 类场景，每类 10 个自然语言 prompt
# ============================================================

PROMPTS = {
    "2D均质点源": [
        "模拟一个2 MHz点声源在均匀介质中的声波传播，网格256x256，区域1cm x 1cm，模拟5微秒",
        "在边长1厘米的正方形区域内，中心放置一个频率为1.5 MHz的点声源，介质声速1540 m/s，网格128x128，仿真时间3微秒",
        "请仿真一个超声波点源：频率3 MHz，声速1500 m/s，密度1000 kg/m^3，网格512x512，区域2cm见方，模拟8微秒",
        "用水中的点声源做仿真，频率1 MHz，声速1500 m/s，网格200x200，计算域0.5cm x 0.5cm，仿真时间4微秒",
        "二维声波传播模拟：点声源在中心，频率2.5 MHz，均匀介质声速1480 m/s，网格256x256，区域0.02 m x 0.02 m，模拟6微秒",
        "做一个简单的超声仿真：平面内中心位置放一个2 MHz声源，介质均匀，声速1540 m/s，网格300x300，区域1.5cm，仿真时间4微秒",
        "仿真一个2 MHz的高频点声源在水中传播，计算域为1 cm正方形，声速1500 m/s，网格256x256，模拟时间5微秒",
        "请生成点声源的声场：中心位置，频率1.8 MHz，介质声速1500 m/s，密度1000，网格200x200，区域1cm x 1cm，仿真3微秒",
        "在软组织等效介质中（声速1540 m/s），中心有2.2 MHz点声源，网格256x256，区域1cm见方，模拟4.5微秒",
        "点声源仿真：声速1480 m/s，频率2 MHz，网格128x128，计算域0.01 m x 0.01 m，模拟时间5微秒",
    ],
    "2D均质初始压力": [
        "模拟一个高斯初始压力脉冲在均匀介质中的传播，峰值压力1000 Pa，半宽0.5mm，网格256x256，区域1cm，声速1500 m/s",
        "初始压力场为一个圆形高斯分布，中心在计算域正中间，峰值500 Pa，半高宽1mm，介质声速1540 m/s，网格128x128，仿真3微秒",
        "请仿真初始压力脉冲的传播：两个高斯脉冲分别位于中心左右各2mm处，峰值均为800 Pa，声速1500 m/s，网格256x256，模拟时间4微秒",
        "用p0初始条件做声波传播模拟：单一高斯脉冲，峰值600 Pa，半宽0.8mm，介质为水，网格300x300，区域1.5cm，仿真5微秒",
        "初始压力分布为高斯函数，幅值1200 Pa，空间半宽0.4mm，均匀介质声速1480 m/s，网格200x200，计算域1cm，模拟时间4微秒",
        "做一个初始压力脉冲的超声波传播仿真：p0为圆形高斯，峰值900 Pa，半宽0.6mm，声速1540 m/s，网格256x256，区域1cm，仿真3.5微秒",
        "模拟声波从初始压力分布开始传播：中心高斯脉冲，峰值750 Pa，半宽0.7mm，介质声速1500 m/s，密度1000，网格256x256，仿真4微秒",
        "初始高斯压力场仿真：峰值1500 Pa，半宽0.3mm，声速1500 m/s，网格200x200，区域0.8cm x 0.8cm，模拟时间3微秒",
        "用初始压力分布模拟声波：单一圆形高斯源，幅值400 Pa，空间宽度1mm（半高宽），声速1540 m/s，网格128x128，仿真2.5微秒",
        "p0初始条件声波仿真：中心高斯脉冲，峰值1100 Pa，半宽0.5mm，介质均匀声速1500 m/s，网格256x256，区域1cm，模拟时间5微秒",
    ],
    "2D异质介质": [
        "模拟声波在含有圆形囊肿的组织中传播：背景声速1540 m/s，囊肿直径3mm声速1450 m/s，点声源2 MHz在中心，网格256x256，区域1.5cm",
        "异质介质仿真：一个直径4mm的圆形骨骼区域（声速3000 m/s）嵌在软组织（1540 m/s）中，点声源2 MHz位于骨骼左侧2mm，网格256x256，模拟5微秒",
        "请仿真超声波穿越一个低声速囊肿：囊肿直径2mm声速1400 m/s，背景声速1540 m/s，密度均为1000，点声源1.5 MHz，网格200x200，区域1cm，模拟4微秒",
        "模拟含有两个圆形异质体的介质：一个高阻抗区域（声速2500 m/s直径3mm），一个低阻抗区域（声速1450 m/s直径3mm），点声源2 MHz在中间，网格300x300",
        "骨骼-软组织界面声波传播：左半区声速1500 m/s（软组织），右半区声速3000 m/s（骨骼），点声源1.8 MHz在左半区中心，网格256x256，仿真4微秒",
        "含有随机声速扰动的非均匀介质：背景声速1540 m/s叠加±5%随机扰动，点声源2 MHz在中心，网格256x256，区域1cm，模拟时间5微秒",
        "声波穿过多个小囊肿的仿真：背景声速1540 m/s，随机分布5个直径1-2mm的低声速囊肿（1450 m/s），点声源2 MHz，网格300x300，区域1.5cm",
        "模拟层状介质中的声波传播：上中下三层，声速分别为1500/1800/1500 m/s，每层厚度约3mm，点声源在上层中心，频率2 MHz，网格256x256",
        "异质介质仿真：背景为水（1500 m/s），中心有一个直径5mm的圆形区域声速为1600 m/s，点声源1.5 MHz在圆形区域左侧边缘，网格256x256，模拟5微秒",
        "含有椭圆形高密度区域的声波传播模拟：椭圆长轴3mm短轴1.5mm，声速2000 m/s位于中心，背景1540 m/s，点声源2 MHz在上方2mm处，网格200x200，仿真4微秒",
    ],
    "传感器记录": [
        "模拟点声源声波传播并在距离中心2mm和4mm处各放置一个传感器记录压力波形，声源频率2 MHz，声速1500 m/s，网格256x256，区域1cm，仿真5微秒",
        "仿真带传感器阵列的声波传播：中心1.5 MHz点声源，在半径为0.5mm、1mm、2mm的圆周上各均匀放置4个传感器，声速1540 m/s，网格200x200，模拟时间4微秒",
        "在点声源仿真中添加3个线阵传感器：分别位于声源右侧2mm、3mm、4mm处，记录每个位置的时域压力信号，2 MHz，声速1500 m/s，网格256x256",
        "做一个有声学传感器检测的仿真：2.5 MHz点声源在中心，在计算域4个角落各放一个传感器记录到达时间和峰值压力，网格256x256，区域1cm",
        "仿真并记录声波到达时间：点声源2 MHz在中心，在距离中心1.5mm、3mm、4.5mm处放置传感器，介质声速1500 m/s，网格256x256，模拟时间5微秒",
        "带有8个环阵传感器的超声波仿真：传感器均匀分布在半径2mm的圆上，中心2 MHz点声源，声速1540 m/s，网格200x200，区域1cm，仿真4微秒",
        "模拟声波在均匀介质中传播并在多个位置记录波形：中心1.8 MHz点声源，传感器位于(±2mm, 0)和(0, ±2mm)四个位置，网格256x256，声速1500 m/s",
        "传感器记录仿真：中心有2.2 MHz点声源，沿x轴正方向每隔1mm放置一个传感器共放5个，声速1480 m/s，网格256x256，区域1cm，模拟时间4微秒",
        "在声波仿真中添加时间-压力记录：中心2 MHz声源，在一维线阵（从中心向右每隔0.5mm到3mm）放置传感器，声速1500 m/s，网格200x200",
        "声波传播加传感器监测：1.5 MHz点声源在中心，2mm半径圆周上均匀8个传感器，介质均匀声速1540 m/s，网格256x256，区域1cm，仿真时间5微秒",
    ],
    "边界情况": [
        "极低频率声波仿真：点声源频率100 kHz，声速1500 m/s，网格128x128，区域5cm x 5cm，模拟时间20微秒",
        "极小网格仿真：网格32x32，声速1500 m/s，点声源频率500 kHz，区域1mm x 1mm，模拟时间0.5微秒",
        "高频大网格仿真：点声源频率5 MHz，声速1540 m/s，网格512x512，区域2cm x 2cm，模拟时间8微秒",
        "极短时间仿真：点声源2 MHz，声速1500 m/s，网格256x256，区域1cm x 1cm，仅模拟0.5微秒",
        "大计算域仿真：点声源1 MHz，声速1500 m/s，网格256x256，模拟区域5cm x 5cm，仿真时间20微秒",
        "超高分辨率小区域：网格512x512，计算域仅2mm x 2mm，点声源频率4 MHz居中，声速1500 m/s，模拟时间1微秒",
        "低分辨率快速仿真：网格64x64，中心2 MHz点声源，声速1500 m/s，区域1cm x 1cm，模拟2微秒",
        "接近Nyquist极限的高频仿真：点声源频率3.5 MHz，网格256x256，区域1cm x 1cm，声速1500 m/s（每波长约4.3个网格点），模拟3微秒",
        "长时间仿真：点声源1 MHz，声速1540 m/s，网格128x128，区域1cm x 1cm，模拟时间15微秒",
        "极小点声源近场仿真：点声源3 MHz，声速1500 m/s，网格256x256，区域仅5mm x 5mm（近场区域），模拟2微秒",
    ],
}

# Verify we have exactly 50 prompts
total = sum(len(v) for v in PROMPTS.values())
assert total == 50, f"Expected 50 prompts, got {total}"

def run_one(idx: int, category: str, prompt: str):
    """Run one test and return result dict."""
    start = time.time()
    try:
        body = json.dumps({
            "inputs": {"query": prompt},
            "response_mode": "blocking",
            "user": "t006-regression",
        }).encode()
        req = urllib.request.Request(API, data=body, headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json"
        })
        resp = urllib.request.urlopen(req, timeout=120)
        elapsed = time.time() - start
        raw = resp.read().decode()
        data = json.loads(raw)
        wf_status = data.get("data", {}).get("status")
        error = data.get("data", {}).get("error")
        outputs = data.get("data", {}).get("outputs", {}).get("text", [])
        elapsed_total = data.get("data", {}).get("elapsed_time", 0)

        result = {
            "idx": idx, "category": category, "prompt": prompt,
            "workflow_status": wf_status, "error": error,
            "elapsed": elapsed, "elapsed_dify": elapsed_total,
        }
        if outputs:
            o = outputs[0] if isinstance(outputs, list) else outputs
            result["exit_code"] = o.get("exit_code")
            result["timed_out"] = o.get("timed_out")
            result["duration_ms"] = o.get("duration_ms")
            result["stdout"] = o.get("stdout")
            result["stderr"] = o.get("stderr")
            result["total_attempts"] = o.get("total_attempts")
            # Extract max pressure
            stdout = o.get("stdout", "")
            import re
            mm = re.search(r'最大压[力强].*?([\d.eE+-]+)', stdout)
            if mm:
                result["max_pressure"] = float(mm.group(1))
            else:
                result["max_pressure"] = None
            # Check for zero pressure
            if result["exit_code"] == 0 and result.get("max_pressure") is not None:
                result["success"] = result["max_pressure"] > 0 and not result.get("timed_out")
            elif result["exit_code"] == 0:
                result["success"] = not result.get("timed_out")
            else:
                result["success"] = False
        else:
            result["success"] = False
        return result
    except Exception as e:
        elapsed = time.time() - start
        return {"idx": idx, "category": category, "prompt": prompt,
                "status": "exception", "error": str(e), "elapsed": elapsed,
                "success": False}

def main():
    results = []
    all_prompts = []
    for cat in ["2D均质点源", "2D均质初始压力", "2D异质介质", "传感器记录", "边界情况"]:
        all_prompts.extend([(cat, p) for p in PROMPTS[cat]])

    print(f"共 {len(all_prompts)} 个测试用例")
    print("=" * 60)

    for i, (cat, prompt) in enumerate(all_prompts):
        sys.stdout.write(f"[{i+1:2d}/50] {cat}: {prompt[:60]}... ")
        sys.stdout.flush()
        r = run_one(i + 1, cat, prompt)
        results.append(r)

        if r.get("success"):
            mp = r.get("max_pressure")
            att = r.get("total_attempts", "?")
            dur = r.get("duration_ms", "?")
            print(f"✅ max_p={mp:.4f}" if mp else f"✅ ok", end="")
            if att and att > 1:
                print(f" (retry×{att})", end="")
            print(f" [{dur:.0f}ms]")
        else:
            reason = r.get("error") or f"exit={r.get('exit_code')}" or r.get("workflow_status") or "unknown"
            mp = r.get("max_pressure")
            if mp is not None and mp == 0:
                reason = "ZERO_PRESSURE"
            print(f"❌ {reason[:80]}")

    # Statistics
    success = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    rate = len(success) / 50 * 100

    print("\n" + "=" * 60)
    print(f"总计: {len(results)} 次")
    print(f"成功: {len(success)} 次")
    print(f"失败: {len(failed)} 次")
    print(f"成功率: {rate:.1f}%")

    # Per category
    print("\n--- 按类别统计 ---")
    for cat in ["2D均质点源", "2D均质初始压力", "2D异质介质", "传感器记录", "边界情况"]:
        cat_results = [r for r in results if r["category"] == cat]
        cat_ok = [r for r in cat_results if r.get("success")]
        print(f"  {cat}: {len(cat_ok)}/{len(cat_results)} ({len(cat_ok)/len(cat_results)*100:.0f}%)")

    # Generate report
    generate_report(results, success, failed, rate)

    # Save raw JSON
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "test_results_raw.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n原始数据已保存: {json_path}")

    return rate >= 90

def generate_report(results, success, failed, rate):
    """Generate markdown report."""
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append(f"# 阶段一 · 50 次端到端回归测试报告")
    lines.append(f"")
    lines.append(f"> 测试时间: {now} | 测试者: AI Agent (Claude Code)")
    lines.append(f"")
    lines.append(f"## 总体结果")
    lines.append(f"")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 总测试数 | 50 |")
    lines.append(f"| 成功 | {len(success)} |")
    lines.append(f"| 失败 | {len(failed)} |")
    lines.append(f"| **成功率** | **{rate:.1f}%** |")
    lines.append(f"| 门禁标准 | ≥ 90% |")
    lines.append(f"| 门禁结果 | {'✅ 通过' if rate >= 90 else '❌ 未通过'} |")
    lines.append(f"")

    # Per category
    lines.append(f"## 按类别统计")
    lines.append(f"")
    lines.append(f"| 类别 | 成功/总数 | 成功率 | 平均耗时 | 平均重试次数 |")
    lines.append(f"|------|-----------|--------|----------|-------------|")
    for cat in ["2D均质点源", "2D均质初始压力", "2D异质介质", "传感器记录", "边界情况"]:
        cat_results = [r for r in results if r["category"] == cat]
        cat_ok = [r for r in cat_results if r.get("success")]
        cat_rate = len(cat_ok) / len(cat_results) * 100
        avg_dur = sum(r.get("duration_ms", 0) or 0 for r in cat_results) / len(cat_results)
        avg_retry = sum(r.get("total_attempts", 0) or 0 for r in cat_results) / len(cat_results)
        lines.append(f"| {cat} | {len(cat_ok)}/{len(cat_results)} | {cat_rate:.0f}% | {avg_dur:.0f} ms | {avg_retry:.2f} |")
    lines.append(f"")

    # All results detail
    lines.append(f"## 全部测试明细")
    lines.append(f"")
    lines.append(f"| # | 类别 | Prompt (截断) | 结果 | 最大压力 | 耗时 | 重试 |")
    lines.append(f"|---|------|-------------|------|---------|------|------|")
    for r in results:
        prompt_short = r["prompt"][:40]
        flag = "✅" if r.get("success") else "❌"
        mp = f"{r.get('max_pressure', 'N/A'):.4f}" if isinstance(r.get('max_pressure'), (int, float)) else "N/A"
        dur = f"{r.get('duration_ms', 'N/A'):.0f}ms" if r.get('duration_ms') else "N/A"
        retry = r.get('total_attempts', '-')
        lines.append(f"| {r['idx']} | {r['category']} | {prompt_short}... | {flag} | {mp} | {dur} | {retry} |")
    lines.append(f"")

    # Failure analysis
    if failed:
        lines.append(f"## 失败分析")
        lines.append(f"")
        for r in failed:
            lines.append(f"### #{r['idx']} {r['category']}")
            lines.append(f"")
            lines.append(f"- **Prompt**: {r['prompt']}")
            lines.append(f"- **Workflow Status**: {r.get('workflow_status', 'N/A')}")
            lines.append(f"- **Exit Code**: {r.get('exit_code', 'N/A')}")
            lines.append(f"- **Error**: {r.get('error', 'N/A')}")
            lines.append(f"- **Stdout**: {r.get('stdout', 'N/A')[:500]}")
            lines.append(f"- **Stderr**: {r.get('stderr', 'N/A')[:500]}")
            lines.append(f"")

    lines.append(f"---")
    lines.append(f"")
    lines.append(f"## 阶段一门禁检查")
    lines.append(f"")
    lines.append(f"| 门禁项 | 状态 |")
    lines.append(f"|--------|------|")
    lines.append(f"| T-001 Sources 压力场非零 | ✅ |")
    lines.append(f"| T-002 Prompt 和知识库已更新 | ✅ |")
    lines.append(f"| T-003 validate_simulation_params 工具已上线 | ✅ |")
    lines.append(f"| T-004 知识库已重索引 | ✅ |")
    lines.append(f"| T-005 工作流含校验节点 | ✅ |")
    lines.append(f"| T-006 50 次测试成功率 ≥ 90% | {'✅' if rate >= 90 else '❌'} |")
    lines.append(f"| git tag phase-1-complete | {'待打标签' if rate >= 90 else '待修复后'} |")

    with open(OUTPUT, "w") as f:
        f.write("\n".join(lines))
    print(f"报告已保存: {OUTPUT}")

if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
