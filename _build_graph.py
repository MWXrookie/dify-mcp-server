"""T-008 工作流改造构造脚本：9 节点 → 13 节点。

在 draft graph 基础上：
1. 代码生成 prompt 末尾注入场数据输出指令（FIELD_OUTPUT_SNIPPET 等价）
2. 新增：解包代码节点 → analyze_simulation_result 工具节点 → 审查 LLM 节点 → 解释 LLM 节点
3. 代码执行节点扩展（合并 report + 审查结论 + 物理解读）
4. 重连边：retry → 解包 → analyze → 审查 → 解释 → 代码执行 → end
5. 输出新 graph JSON 到 stdout（由外层写回 DB）

用法：python3 build_graph.py <draft_graph.json> > new_graph.json
"""

import json
import sys

RETRY_NODE = "5655556822808"
CODE_EXEC_NODE = "1786278074940"
END_NODE = "1783992518452"
CODE_GEN_NODE = "1783991079665"

# 新节点 id（大数字避免冲突）
UNPACK = "1786091111001"
ANALYZE = "1786091111002"
REVIEW = "1786091111003"
EXPLAIN = "1786091111004"

FIELD_OUTPUT_INSTRUCTION = """\n\n# 场数据输出（必须！最后输出压力场 JSON 供分析）
仿真完成后，将"全时最大绝对压力场"按以下标记格式打印到 stdout，用于结果分析/热力图：
__ACOU_FIELD_START__
{"shape": [Nx, Ny], "kind": "field", "data": [[...]]}
__ACOU_FIELD_END__
参考实现（在仿真代码末尾追加）：
import json as __json
import jax.numpy as __jnp
__field = __jnp.max(__jnp.abs(p.params), axis=0)[..., 0]
print("__ACOU_FIELD_START__")
print(__json.dumps({"shape": list(__field.shape), "kind": "field", "data": __field.tolist()}))
print("__ACOU_FIELD_END__")
print(f"最大压力: {float(__jnp.max(__field)):.6f}")
"""

REVIEW_PROMPT = """你是声学仿真结果审查员。根据分析结果判断这次仿真是否通过。

仿真分析结果（JSON）：
{{#1786091111002.json#}}

判定规则：
- verdict 字段为 normal 且 max_pressure > 0 → 输出 pass
- verdict 字段为 zero_field（全场压力为零）→ 输出 retry
- verdict 字段为 abnormal 或执行失败 → 输出 fail

输出格式（严格二选一）：
- 通过：pass
- 需重试：retry
- 彻底失败：fail
只输出这三个词之一，不要输出任何其他文字。"""

EXPLAIN_PROMPT = """你是声学仿真讲解员。根据仿真分析结果，用 3 句以上自然语言向用户解读这次仿真，
包含具体数值和物理直觉（例如波峰位置、传播距离、几何衰减是否符合预期）。

仿真分析结果（JSON）：
{{#1786091111002.json#}}

请直接输出解读内容，不要输出 JSON 或代码。"""

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

MERGE_CODE = """import json
import re

def _strip_think(text):
    if not text:
        return ""
    return re.sub(r"<think>.*?</think>", "", str(text), flags=re.DOTALL).strip()

def main(mcp_json, review_text, explanation):
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
    if result:
        return {"result": result}
    return {"result": json.dumps(data, ensure_ascii=False, indent=2)}"""


def _uid() -> str:
    import uuid
    return str(uuid.uuid4())


def make_llm_node(nid, title, prompt, x, y):
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
            "model": {
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


def make_code_node(nid, title, code, variables, x, y, outputs=None):
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


def _param_schema(name, ptype, required, desc=""):
    return {
        "llm_description": desc,
        "human_description": {"ja_JP": "", "en_US": "", "pt_BR": "", "zh_Hans": ""},
        "form": "llm", "multiple": False, "template": None, "scope": None,
        "name": name,
        "label": {"ja_JP": name, "en_US": name, "pt_BR": name, "zh_Hans": name},
        "placeholder": None, "options": [], "min": None, "default": None,
        "auto_generate": None, "required": required, "input_schema": None,
        "type": ptype, "max": None, "precision": None,
    }


def make_analyze_tool_node(x, y):
    return {
        "sourcePosition": "right", "targetPosition": "left", "zIndex": 0,
        "id": ANALYZE,
        "positionAbsolute": {"x": x, "y": y},
        "data": {
            "isInIteration": False, "isInLoop": False, "tool_node_version": "2",
            "tool_configurations": {},
            "provider_icon": {"background": "#6366F1", "content": "🔗"},
            "provider_show_name": "jwave-mcp",
            "params": {"stdout_text": "", "stderr_text": "", "exit_code": "", "params_json": ""},
            "tool_description": "Analyze a jwave simulation output: physics summary + heatmap/waveform + verdict.",
            "provider_name": "jwave-mcp",
            "tool_name": "analyze_simulation_result",
            "tool_parameters": {
                "stdout_text": {"value": f"{{{{#{UNPACK}.stdout#}}}}", "type": "mixed"},
                "stderr_text": {"value": f"{{{{#{UNPACK}.stderr#}}}}", "type": "mixed"},
                "exit_code": {"value": f"{{{{#{UNPACK}.exit_code#}}}}", "type": "mixed"},
                "params_json": {"value": "{}", "type": "constant"},
            },
            "is_team_authorization": True,
            "meta": None,
            "plugin_unique_identifier": "",
            "provider_type": "mcp",
            "provider_id": "jwave-mcp",
            "title": "analyze_simulation_result",
            "paramSchemas": [
                _param_schema("stdout_text", "string", True, "仿真 stdout 文本"),
                _param_schema("stderr_text", "string", False, "仿真 stderr 文本"),
                _param_schema("exit_code", "number", False, "退出码"),
                _param_schema("params_json", "string", False, "仿真参数 JSON"),
            ],
            "plugin_id": "",
            "provider_icon_dark": None,
            "tool_label": "analyze_simulation_result",
            "type": "tool",
            "selected": False,
        },
        "position": {"x": x, "y": y},
        "type": "custom", "height": 83, "selected": False, "width": 241,
    }


def main():
    src = json.load(open(sys.argv[1], encoding="utf-8"))
    nodes = src["nodes"]
    edges = src["edges"]

    # 1) 代码生成 prompt 注入场输出指令
    for n in nodes:
        if n["id"] == CODE_GEN_NODE:
            for msg in n["data"]["prompt_template"]:
                if msg.get("role") == "user":
                    msg["text"] = msg["text"].rstrip() + FIELD_OUTPUT_INSTRUCTION

    # 2) 代码执行节点改造：多输入 + 合并逻辑
    for n in nodes:
        if n["id"] == CODE_EXEC_NODE:
            n["data"]["code"] = MERGE_CODE
            n["data"]["variables"] = [
                {"variable": "mcp_json", "value_selector": [RETRY_NODE, "json"], "value_type": "array[object]"},
                {"variable": "review_text", "value_selector": [REVIEW, "text"], "value_type": "string"},
                {"variable": "explanation", "value_selector": [EXPLAIN, "text"], "value_type": "string"},
            ]

    # 3) 新增 4 个节点
    new_nodes = [
        make_code_node(UNPACK, "解包仿真结果", UNPACK_CODE,
                       [{"variable": "mcp_json", "value_selector": [RETRY_NODE, "json"], "value_type": "array[object]"}],
                       2140, 200,
                       outputs={
                           "stdout": {"type": "string", "children": None},
                           "stderr": {"type": "string", "children": None},
                           "exit_code": {"type": "number", "children": None},
                       }),
        make_analyze_tool_node(2320, 200),
        make_llm_node(REVIEW, "结果审查", REVIEW_PROMPT, 2500, 200),
        make_llm_node(EXPLAIN, "结果解释", EXPLAIN_PROMPT, 2680, 200),
    ]
    nodes.extend(new_nodes)

    # 4) 重连边
    edges = [e for e in edges if e["source"] != RETRY_NODE or e["target"] != CODE_EXEC_NODE]
    edges = [e for e in edges if e["source"] != CODE_GEN_NODE or e["target"] != RETRY_NODE]
    new_edges = [
        {"id": _uid(), "source": CODE_GEN_NODE, "target": RETRY_NODE,
         "sourceHandle": "source", "targetHandle": "target", "type": "default"},
        {"id": _uid(), "source": RETRY_NODE, "target": UNPACK,
         "sourceHandle": "source", "targetHandle": "target", "type": "default"},
        {"id": _uid(), "source": UNPACK, "target": ANALYZE,
         "sourceHandle": "source", "targetHandle": "target", "type": "default"},
        {"id": _uid(), "source": ANALYZE, "target": REVIEW,
         "sourceHandle": "source", "targetHandle": "target", "type": "default"},
        {"id": _uid(), "source": REVIEW, "target": EXPLAIN,
         "sourceHandle": "source", "targetHandle": "target", "type": "default"},
        {"id": _uid(), "source": EXPLAIN, "target": CODE_EXEC_NODE,
         "sourceHandle": "source", "targetHandle": "target", "type": "default"},
    ]
    edges.extend(new_edges)

    src["nodes"] = nodes
    src["edges"] = edges
    print(json.dumps(src, ensure_ascii=False))


if __name__ == "__main__":
    main()
