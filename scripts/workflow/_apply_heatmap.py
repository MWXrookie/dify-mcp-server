"""热力图可视化落地：工作流合并节点把 analyze 热力图嵌入报告（幂等）。

更新两个合并节点：
- 1786278074940 (MERGE1)：加 analyze_json 输入 + 热力图 Markdown 嵌入
- 1786095555007 (MERGE2)：热力图嵌入 + 修复 analyze_json 解析（重试解读为空 bug）

用法: python3 _apply_heatmap.py <graph.json> > new_graph.json
"""

import json
import sys

MERGE1 = "1786278074940"
MERGE2 = "1786095555007"
ANALYZE1 = "1786091111002"
ANALYZE2 = "1786095555006"

_COMMON_PRELUDE = """\
import json
import re


def _strip_think(text):
    if not text:
        return ""
    return re.sub(r"<think>.*?</think>", "", str(text), flags=re.DOTALL).strip()


def _find_analyze(analyze_json):
    \"\"\"从 Dify json 变量提取 analyze 返回 dict（兼容嵌套 list/dict/data 包裹）。\"\"\"
    if analyze_json is None:
        return {}
    an = analyze_json
    if isinstance(an, str):
        try:
            an = json.loads(an)
        except Exception:
            return {}
    if isinstance(an, list):
        if not an:
            return {}
        an = an[0]
    if isinstance(an, dict) and isinstance(an.get("data"), list) and an["data"]:
        an = an["data"][0]
    return an if isinstance(an, dict) else {}


def _heatmap_md(analyze_json):
    an = _find_analyze(analyze_json)
    b64 = an.get("heatmap_png_base64")
    if b64:
        return f"\\n\\n![压力场热力图](data:image/png;base64,{b64})"
    return ""


"""

MERGE1_CODE = _COMMON_PRELUDE + """\
def main(mcp_json, review_text, explanation, analyze_json):
    data = mcp_json
    if isinstance(data, list) and len(data) > 0:
        data = data[0]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return {"result": str(data)}
    if not isinstance(data, dict):
        return {"result": str(data)}

    report = data.get("report", "")
    parts = []
    if report:
        parts.append(report)

    verdict = _strip_think(review_text).lower()
    if verdict and verdict != "pass":
        parts.append(f"\\n\\n> ⚠️ **审查结论：{verdict}**（结果疑似异常，建议检查参数后重试）")

    expl = _strip_think(explanation)
    if expl:
        parts.append(f"\\n\\n---\\n\\n## 🧠 物理解读\\n\\n{expl}")

    result = "\\n".join(p for p in parts if p)
    result += _heatmap_md(analyze_json)
    if result:
        return {"result": result}
    return {"result": json.dumps(data, ensure_ascii=False, indent=2)}"""

MERGE2_CODE = _COMMON_PRELUDE + """\
def main(mcp_json, analyze_json):
    data = mcp_json
    if isinstance(data, list) and len(data) > 0:
        data = data[0]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return {"result": str(data)}
    if not isinstance(data, dict):
        return {"result": str(data)}

    report = data.get("report", "")
    parts = []
    if report:
        parts.append(report)

    parts.append("\\n\\n---\\n\\n> 🔁 **已自动重试一次**（首次结果未通过物理审查）")

    an = _find_analyze(analyze_json)
    if an:
        parts.append(f"\\n\\n## 🧠 重试后解读\\n\\n{an.get('summary', '')}")

    result = "\\n".join(p for p in parts if p)
    result += _heatmap_md(analyze_json)
    if result:
        return {"result": result}
    return {"result": json.dumps(data, ensure_ascii=False, indent=2)}"""


def main():
    g = json.load(open(sys.argv[1], encoding="utf-8"))
    marker = "_heatmap_md"
    for n in g.get("nodes", []):
        nid = n.get("id")
        d = n.get("data", {})
        if nid == MERGE1:
            if marker not in d.get("code", ""):
                d["code"] = MERGE1_CODE
                vars_ = d.setdefault("variables", [])
                if not any(v.get("variable") == "analyze_json" for v in vars_):
                    vars_.append({
                        "variable": "analyze_json",
                        "value_selector": [ANALYZE1, "json"],
                        "value_type": "string",
                    })
        elif nid == MERGE2:
            if marker not in d.get("code", ""):
                d["code"] = MERGE2_CODE
    print(json.dumps(g, ensure_ascii=False))


if __name__ == "__main__":
    main()
