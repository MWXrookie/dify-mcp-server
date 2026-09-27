"""Guard rails: the prompts must stay byte-identical to the Dify workflow."""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from jwave_flow import prompts

YML = Path(__file__).resolve().parent.parent / "dify_workflow" / "仿真.yml"

MAP = {
    "{{#1783990934733.query#}}": "{query}",
    "{{#1783990989034.output#}}": "{kb_context}",
    "{{#1783991048409.text#}}": "{code_ref}",
    "{{#1783994256713.code_final#}}": "{code_final}",
    "{{#context#}}": "{context}",
    "{{#1783994422790.stderr#}}": "{stderr}",
}


def _nodes():
    data = yaml.safe_load(YML.read_text(encoding="utf-8"))
    return {n["id"]: n["data"] for n in data["workflow"]["graph"]["nodes"]}


def _user_text(nodes, node_id):
    return next(m["text"] for m in nodes[node_id]["prompt_template"] if m["role"] == "user")


def _convert(text):
    for src, dst in MAP.items():
        text = text.replace(src, dst)
    return text


def test_prompts_are_verbatim():
    nodes = _nodes()
    assert prompts.REQUIREMENT_ANALYST_USER == _convert(_user_text(nodes, "1783990970058"))
    assert prompts.PARAM_EXTRACT_USER == _convert(_user_text(nodes, "1783991048409"))
    assert prompts.CODE_GENERATE_USER == _convert(_user_text(nodes, "1783991079665"))
    assert prompts.CODE_FIX_USER == _convert(_user_text(nodes, "1784023398114"))
    assert prompts.TEMPLATE_TRANSFORM == nodes["1783990989034"]["template"]


def test_graph_shape_matches_dify():
    """The translated graph must keep the same nodes and edges."""
    data = yaml.safe_load(YML.read_text(encoding="utf-8"))
    graph = data["workflow"]["graph"]
    types = {n["id"]: n["data"]["type"] for n in graph["nodes"]}
    assert types["1783990934733"] == "start"
    assert types["1783992518452"] == "end"
    assert types["1783994256713"] == "loop"
    edges = {(e["source"], e["target"]) for e in graph["edges"]}
    assert ("1783991079665", "1783994256713") in edges      # 代码生成 -> 循环
    assert ("1783990934733", "1783990970058") in edges      # start -> 需求分析
    assert ("1783991048409", "1783991079665") in edges      # 参数提取 -> 代码生成
