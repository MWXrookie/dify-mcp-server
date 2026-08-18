"""多轮对话稳定性测试：连续多轮增量修改，验证「合并 + 仿真」链路稳定。

用法: python test_multiturn_stability.py [重复次数]   （默认 2 遍，每遍 7 轮）
结果写入 test_multiturn_result.json（UTF-8）。
"""
import json
import sys
import time
import urllib.request

BASE = "http://192.168.30.200:8001"

# (本轮输入, 是否预期触发合并)
TURNS = [
    ("模拟一个2 MHz点声源在均匀介质中的声波传播，网格128x128，区域1cm x 1cm，模拟5微秒，声速1500 m/s", False),
    ("把频率改成3 MHz", True),
    ("把网格改成256x256", True),
    ("把区域改成1.5cm", True),
    ("在距离中心2mm处放一个传感器记录压力波形", True),
    ("把声速改成1540 m/s", True),
    ("把仿真时长改成3微秒", True),
]


def chat(message, requirement=""):
    body = json.dumps({"message": message, "requirement": requirement}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read().decode("utf-8"))


def run_sequence(round_no):
    requirement = ""
    results = []
    for i, (msg, expect_merge) in enumerate(TURNS, 1):
        t0 = time.time()
        try:
            d = chat(msg, requirement)
            elapsed = round(time.time() - t0, 1)
            ok = d.get("workflow_status") == "succeeded"
            results.append({
                "round": round_no, "turn": i, "message": msg,
                "ok": ok, "elapsed": elapsed,
                "workflow_status": d.get("workflow_status"),
                "merge_used": d.get("merge_used"),
                "expect_merge": expect_merge,
                "requirement": d.get("requirement", ""),
                "report_head": (d.get("report", "") or "")[:120],
            })
            requirement = d.get("requirement", "") or requirement
        except Exception as e:
            elapsed = round(time.time() - t0, 1)
            results.append({
                "round": round_no, "turn": i, "message": msg,
                "ok": False, "elapsed": elapsed, "error": str(e),
                "requirement": requirement,
            })
    return results


def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    all_results = []
    for r in range(1, rounds + 1):
        print(f"running round {r}/{rounds} ...", flush=True)
        all_results.extend(run_sequence(r))

    ok = [x for x in all_results if x.get("ok")]
    fail = [x for x in all_results if not x.get("ok")]
    lat = [x["elapsed"] for x in all_results]

    with open("test_multiturn_result.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print("=" * 50)
    print(f"总轮次: {len(all_results)}")
    print(f"成功: {len(ok)} / 失败: {len(fail)}")
    print(f"成功率: {round(len(ok) / len(all_results) * 100, 1)}%")
    if lat:
        print(f"平均耗时: {round(sum(lat) / len(lat), 1)}s  最长: {round(max(lat), 1)}s")
    for x in fail:
        print("FAIL ->", x.get("round"), "-", x.get("turn"),
              "|", x.get("error") or x.get("workflow_status"),
              "|", x.get("message"))


if __name__ == "__main__":
    main()
