#!/usr/bin/env python3
"""Re-test only the 10 初始压力 prompts after p0 prompt fix."""
import json, time, sys, urllib.request, re

API = "http://localhost/v1/workflows/run"
import os
TOKEN = os.environ.get("DIFY_API_KEY", "")

PROMPTS = [
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
]

def run_one(idx, prompt):
    start = time.time()
    try:
        body = json.dumps({"inputs": {"query": prompt}, "response_mode": "blocking", "user": "p0-retest"}).encode()
        req = urllib.request.Request(API, data=body, headers={
            "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"
        })
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read().decode())
        elapsed = time.time() - start

        wf = data.get("data", {})
        outputs = wf.get("outputs", {}).get("text", [])
        result = {"idx": idx, "prompt": prompt, "elapsed": elapsed, "wf_status": wf.get("status")}

        if outputs:
            o = outputs[0] if isinstance(outputs, list) else outputs
            result["exit_code"] = o.get("exit_code")
            result["timed_out"] = o.get("timed_out")
            result["stdout"] = o.get("stdout")
            result["attempts"] = o.get("total_attempts")
            mm = re.search(r'(?:最大压[力强]|max(?:imum)?\s+pressure)\s*[：:]\s*([\d.eE+-]+)', o.get("stdout", ""), re.IGNORECASE)
            result["max_pressure"] = float(mm.group(1)) if mm else None
            result["success"] = (o.get("exit_code") == 0 and not o.get("timed_out")
                                and result.get("max_pressure") is not None and result["max_pressure"] > 0.001)
        else:
            result["success"] = False
        return result
    except Exception as e:
        return {"idx": idx, "prompt": prompt, "success": False, "error": str(e)}

results = []
for i, p in enumerate(PROMPTS):
    sys.stdout.write(f"[{i+1:2d}/10] {p[:60]}... ")
    sys.stdout.flush()
    r = run_one(i+1, p)
    results.append(r)
    if r.get("success"):
        print(f"✅ max_p={r['max_pressure']:.4f} [{r.get('attempts','?')} attempts]")
    else:
        reason = "ZERO" if r.get("max_pressure") == 0 else (r.get("error") or f"exit={r.get('exit_code')}")
        print(f"❌ {reason}")

ok = sum(1 for r in results if r["success"])
print(f"\n结果: {ok}/10 ({ok*10}%)")
for r in results:
    status = "✅" if r["success"] else "❌"
    print(f"  {status} #{r['idx']}: max_p={r.get('max_pressure','N/A')}, attempts={r.get('attempts','N/A')}")
