"""T-009 迭代循环构造脚本（预展开方案）：13 节点 → 21 节点。

在已发布工作流基础上：
1. 审查节点后加 if-else 条件分支（新版 cases schema）：
   - case "pass"（审查输出含 pass）→ 现有解释 → 合并 → 原 end
   - ELSE（retry/fail）→ 参数提取2（prompt 注入审查建议）→ 代码生成2 → MCP retry2
     → 解包2 → analyze2 → 合并2（report + 解读 + 重试提示）→ 新 end2
2. 迭代上限 = 2 次尝试（首次 + 1 次参数级重试），静态预展开保证终止。

用法: python3 _build_t009.py <base_graph.json> > new_graph.json
"""

import json
import sys
import uuid

REVIEW = "1786091111003"       # 审查节点（现有）
EXPLAIN = "1786091111004"      # 解释节点（现有）
MERGE1 = "1786278074940"       # 合并节点（现有）
END1 = "1783992518452"         # 原 end（现有）
PARAM1 = "1783991048409"       # 参数提取（现有，取其 prompt 作副本模板）
GEN1 = "1783991079665"         # 代码生成（现有）
RETRY1 = "5655556822808"       # MCP retry（现有）
UNPACK1 = "1786091111001"      # 解包（现有）
ANALYZE1 = "1786091111002"     # analyze（现有）

# 新节点 id
IF1 = "1786095555001"
PARAM2 = "1786095555002"
GEN2 = "1786095555003"
RETRY2 = "1786095555004"
UNPACK2 = "1786095555005"
ANALYZE2 = "1786095555006"
MERGE2 = "1786095555007"
END2 = "1786095555008"

REVIEW_SUGGEST_PROMPT = (
    "\n\n# 重要：上一轮仿真结果未通过审查\n"
    "上一轮审查结论：{{#1786091111003.text#}}\n"
    "如果问题出在参数（如网格过小、频率-分辨率不匹配、时间不足等），"
    "请根据审查建议修正参数后重新提取；参数合理则保持原参数。"
)

# 审查节点 prompt 增强：量级合理性（写回现有审查节点）
REVIEW_PROMPT_ENHANCEMENT = (
    "\n\n# 量级合理性（重要）\n"
    "注意核对分析 JSON 中的 max_pressure 数值：若 max_pressure 极小（如 < 0.001 Pa）"
    "或量级明显异常（超声仿真通常应在 Pa~kPa 量级），即使 verdict 为 normal，"
    "也应输出 retry（可能网格/频率分辨率不足导致场几乎全零）。"
)

UNPACK_CODE = """import json

def main(mcp_json):
    data = mcp_json
    if isinstance(data, list) and len(data) > 0:
        data = data[0]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return {"stdout": "", "stderr": "", "exit_code": 1}
    if not isinstance(data, dict):
        return {"stdout": "", "stderr": "", "exit_code": 1}
    ec = data.get("exit_code")
    if ec is None:
        ec = 1
    return {
        "stdout": data.get("stdout", "") or "",
        "stderr": data.get("stderr", "") or "",
        "exit_code": ec,
    }"""

MERGE2_CODE = """import json

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

    an = analyze_json
    if isinstance(an, str):
        try:
            an = json.loads(an)
        except Exception:
            an = None
    if isinstance(an, dict):
        parts.append(f"\\n\\n## 🧠 重试后解读\\n\\n{an.get('summary', '')}")

    result = "\\n".join(p for p in parts if p)
    if result:
        return {"result": result}
    return {"result": json.dumps(data, ensure_ascii=False, indent=2)}"""


def _uid():
    return str(uuid.uuid4())


def clone_llm(nid, title, prompt, x, y, model=None):
    return {
        "sourcePosition": "right", "targetPosition": "left", "zIndex": 0,
        "id": nid,
        "positionAbsolute": {"x": x, "y": y},
        "data": {
            "prompt_template": [
                {"id": _uid(), "role": "system", "text": ""},
                {"id": _uid(), "role": "user", "text": prompt},
            ],
            "context": {"enabled": False, "variable_selector": []},
            "structured_output_enabled": False,
            "title": title,
            "type": "llm",
            "vision": {"enabled": False},
            "model": model or {
                "name": "deepseek-v4-flash",
                "provider": "langgenius/deepseek/deepseek",
                "completion_params": {"temperature": 0.3},
                "mode": "chat",
            },
            "selected": False,
        },
        "position": {"x": x, "y": y},
        "type": "custom", "height": 87, "selected": False, "width": 241,
    }


def make_ifelse(x, y):
    return {
        "sourcePosition": "right", "targetPosition": "left", "zIndex": 0,
        "id": IF1,
        "positionAbsolute": {"x": x, "y": y},
        "data": {
            "type": "if-else",
            "title": "审查结果分支",
            "cases": [
                {
                    "case_id": "pass",
                    "logical_operator": "and",
                    "conditions": [
                        {
                            "variable_selector": [REVIEW, "text"],
                            "comparison_operator": "contains",
                            "value": "pass",
                        }
                    ],
                }
            ],
            "selected": False,
        },
        "position": {"x": x, "y": y},
        "type": "custom", "height": 87, "selected": False, "width": 241,
    }


def clone_tool(src_node, nid, title, param_overrides, x, y):
    """克隆现有工具节点（retry/analyze），替换 id/title/tool_parameters。"""
    node = json.loads(json.dumps(src_node, ensure_ascii=False))
    node["id"] = nid
    node["positionAbsolute"] = {"x": x, "y": y}
    node["position"] = {"x": x, "y": y}
    d = node["data"]
    d["title"] = title
    d["tool_label"] = title
    for k, v in param_overrides.items():
        if k in d["tool_parameters"]:
            d["tool_parameters"][k] = v
    return node


def make_code(nid, title, code, variables, x, y, outputs=None):
    if outputs is None:
        outputs = {"result": {"type": "string", "children": None}}
    return {
        "sourcePosition": "right", "targetPosition": "left", "zIndex": 0,
        "id": nid,
        "positionAbsolute": {"x": x, "y": y},
        "data": {
            "code": code,
            "code_language": "python3",
            "title": title,
            "outputs": outputs,
            "type": "code",
            "variables": variables,
            "selected": False,
        },
        "position": {"x": x, "y": y},
        "type": "custom", "height": 51, "selected": False, "width": 241,
    }


def make_end(x, y):
    return {
        "sourcePosition": "right", "targetPosition": "left", "zIndex": 0,
        "id": END2,
        "positionAbsolute": {"x": x, "y": y},
        "data": {
            "type": "end",
            "title": "输出(重试)",
            "outputs": [
                {"value_selector": [MERGE2, "result"], "value_type": "string", "variable": "text"}
            ],
            "selected": False,
        },
        "position": {"x": x, "y": y},
        "type": "custom", "height": 87, "selected": False, "width": 241,
    }


def main():
    src = json.load(open(sys.argv[1], encoding="utf-8"))
    nodes = {n["id"]: n for n in src["nodes"]}

    # 0) 增强现有审查节点 prompt（量级合理性判断）
    if REVIEW in nodes:
        for msg in nodes[REVIEW]["data"].get("prompt_template", []):
            if msg.get("role") == "user" and REVIEW_PROMPT_ENHANCEMENT not in msg["text"]:
                msg["text"] = msg["text"].rstrip() + REVIEW_PROMPT_ENHANCEMENT

    # 提取现有 prompt 作副本模板
    param1_prompt = ""
    gen1_prompt = ""
    gen1_model = None
    for msg in nodes[PARAM1]["data"].get("prompt_template", []):
        if msg.get("role") == "user":
            param1_prompt = msg["text"]
    for msg in nodes[GEN1]["data"].get("prompt_template", []):
        if msg.get("role") == "user":
            gen1_prompt = msg["text"]
    gen1_model = nodes[GEN1]["data"].get("model")

    new_nodes = [
        make_ifelse(2680, 320),
        clone_llm(PARAM2, "参数提取(重试)", param1_prompt + REVIEW_SUGGEST_PROMPT, 2880, 320),
        clone_llm(GEN2, "代码生成(重试)", gen1_prompt, 3060, 320, model=gen1_model),
        clone_tool(nodes[RETRY1], RETRY2, "run_jwave_code_with_retry(重试)",
                   {"code": {"value": f"{{{{#{GEN2}.text#}}}}", "type": "mixed"}}, 3240, 320),
        make_code(UNPACK2, "解包仿真结果(重试)", UNPACK_CODE,
                  [{"variable": "mcp_json", "value_selector": [RETRY2, "json"], "value_type": "array[object]"}],
                  3420, 320,
                  outputs={"stdout": {"type": "string", "children": None},
                           "stderr": {"type": "string", "children": None},
                           "exit_code": {"type": "number", "children": None}}),
        clone_tool(nodes[ANALYZE1], ANALYZE2, "analyze_simulation_result(重试)",
                   {"stdout_text": {"value": f"{{{{#{UNPACK2}.stdout#}}}}", "type": "mixed"},
                    "stderr_text": {"value": f"{{{{#{UNPACK2}.stderr#}}}}", "type": "mixed"},
                    "exit_code": {"value": f"{{{{#{UNPACK2}.exit_code#}}}}", "type": "mixed"}},
                   3600, 320),
        make_code(MERGE2, "合并输出(重试)", MERGE2_CODE,
                  [{"variable": "mcp_json", "value_selector": [RETRY2, "json"], "value_type": "array[object]"},
                   {"variable": "analyze_json", "value_selector": [ANALYZE2, "json"], "value_type": "string"}],
                  3780, 320),
        make_end(3960, 320),
    ]
    src["nodes"].extend(new_nodes)

    # 重接边：删 审查→解释，加分支链
    edges = [e for e in src["edges"] if not (e["source"] == REVIEW and e["target"] == EXPLAIN)]
    new_edges = [
        {"id": _uid(), "source": REVIEW, "target": IF1,
         "sourceHandle": "source", "targetHandle": "target", "type": "default"},
        {"id": _uid(), "source": IF1, "target": EXPLAIN,
         "sourceHandle": "pass", "targetHandle": "target", "type": "default"},
        {"id": _uid(), "source": IF1, "target": PARAM2,
         "sourceHandle": "false", "targetHandle": "target", "type": "default"},
        {"id": _uid(), "source": PARAM2, "target": GEN2,
         "sourceHandle": "source", "targetHandle": "target", "type": "default"},
        {"id": _uid(), "source": GEN2, "target": RETRY2,
         "sourceHandle": "source", "targetHandle": "target", "type": "default"},
        {"id": _uid(), "source": RETRY2, "target": UNPACK2,
         "sourceHandle": "source", "targetHandle": "target", "type": "default"},
        {"id": _uid(), "source": UNPACK2, "target": ANALYZE2,
         "sourceHandle": "source", "targetHandle": "target", "type": "default"},
        {"id": _uid(), "source": ANALYZE2, "target": MERGE2,
         "sourceHandle": "source", "targetHandle": "target", "type": "default"},
        {"id": _uid(), "source": MERGE2, "target": END2,
         "sourceHandle": "source", "targetHandle": "target", "type": "default"},
    ]
    edges.extend(new_edges)
    src["edges"] = edges
    print(json.dumps(src, ensure_ascii=False))


if __name__ == "__main__":
    main()
