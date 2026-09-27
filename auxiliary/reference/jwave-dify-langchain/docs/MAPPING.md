# Dify → LangChain/LangGraph 映射表

原始工作流：`dify_workflow/仿真.yml`（Dify app「仿真」，`kind: app`, `version: 0.6.0`）

## 节点映射

| # | Dify 节点 (id) | 类型 | LangGraph 节点 | 实现位置 |
|---|----------------|------|----------------|----------|
| ① | 用户输入 `1783990934733` | start | 图输入 `state["query"]` | `cli.py` |
| ② | LLM `1783990970058` | llm (需求分析) | `analyze` | `graph.py::n_analyze` |
| ③ | 知识检索 `1783990977543` | knowledge-retrieval | `retrieve` | `graph.py::n_retrieve` → `knowledge.py` |
| ④ | 模板转换 `1783990989034` | template-transform | `template` | `graph.py::n_template` → `knowledge.render_template_transform` |
| ⑤ | 参数提取 `1783991048409` | llm | `extract` | `graph.py::n_extract` |
| ⑥ | 代码生成 `1783991079665` | llm (structured `{code}`) | `generate` | `graph.py::n_generate` |
| ➕ | **（Dify 无此节点）** | — | `param_check` ④b | `graph.py::n_param_check` → `physics.py`（方案一） |
| ➕ | **（Dify 无此节点）** | — | `static_check` ⑤b | `graph.py::n_static_check` → `static_check.py`（方案二） |
| ➕ | **（Dify 无此节点）** | — | `semantic_gate` ⑥b | `graph.py::n_semantic_gate` → `semantic.py`（方案三） |
| ⑦ | 循环 `1783994256713` | loop (`loop_count=10`) | `run_code ⇄ fix_code` 环 + `max_iterations` | `graph.py::_build/_route_after_run` |
| ⑦a | `run_python_code` `1783994373881` | tool (**MCP**, 已失效) | `run_code` | `graph.py::n_run` → `executor.py` |
| ⑦b | 代码执行 2 `1783994422790` | code | **合并进 executor 返回值** | `executor.py::ExecutionResult` |
| ⑦c | 条件分支 `1784110105080` | if-else (`stderr` empty) | `_route_after_run` | `graph.py::_route_after_run` |
| ⑦d | 代码纠错 `1784023398114` | llm (structured `{code_2}`) | `fix_code` | `graph.py::n_fix` |
| ⑦e | 变量赋值 `1784024297685` | assigner (`code_final = 纠错.text`) | `state["code_final"] = ...` | `graph.py::n_fix` |
| ⑦f | 退出循环 `1784110125544` | loop-end | → `finalize` | `graph.py` |
| ⑧ | 输出 `1783992518452` | end (`code_final`) | `finalize` / `state["text"]` | `graph.py::n_finalize` |

## 关键差异与决策

| 主题 | Dify 原实现 | 本实现 | 原因 |
|------|-------------|--------|------|
| 模型 | marketplace 插件 `deepseek-v4-pro` / `deepseek-coder` | **OpenAI 兼容接口**，默认 `deepseek-flash`（`ANALYST_MODEL` / `CODER_MODEL` 可分别覆盖） | 可移植性；换 vLLM/Ollama/OpenAI 只改 env |
| 结构化输出 | 插件侧 JSON Schema (`{code}` / `{code_2}`) | 优先 `with_structured_output`，失败自动回退到纯文本 + 去 ``` 围栏 | 并非所有 OpenAI 兼容端点都支持 `response_format`/tool calling |
| 知识库 | 云端数据集 + `qwen3-rerank` 重排，`top_k=4` | 本地 markdown + **BM25**（默认，零依赖）；可选 `openai` embedding 后端；保留 `top_k=4` | 可移植、可离线；重排仅在 embedding 后端下才有意义 |
| 代码执行 | `RUN_PYTHON_CODE` MCP 工具（失效） | **可插拔执行器**：`subprocess`(默认) / `jupyter` / `mcp` / `auto` | MCP 服务器已失效；三种后端都复刻同一返回契约 |
| ANSI 转义 | 「代码执行 2」节点用 `simple_strip_ansi` 清洗 | `executor.strip_ansi()` 对 jupyter/mcp 输出做同样清洗 | 保持与 Dify 一致（否则 `stderr` 判空会误判） |
| `stderr` 判空 | `comparison_operator: empty` | `ExecutionResult.ok = stderr.strip() == ""` | 1:1 复刻循环退出条件 |
| 循环上限 | `loop_count = 10` | `LOOP_MAX_ITERATIONS=10` | 1:1 复刻；超限输出当前代码 |
| 「需求分析」节点 | 输出**未被任何下游节点引用** | 保留为 `analyze` 节点（仅在 trace 中可见） | 忠实保留原图；见下方说明 |

## 说明：① 需求分析 是一个「悬空」节点

在原始 Dify 图中，`1783990970058`(需求分析) 的文本输出**没有被任何下游节点引用**：
知识检索用的是原始 `query`（`query_variable_selector: [1783990934733, query]`），
参数提取/代码生成也不引用它。它只参与了图的走向（`llm → knowledge-retrieval`）。

本实现忠实保留该节点（可在 trace 中看到「① 需求分析 完成」），
若你希望它真正参与下游提示词，只需把 `n_retrieve` / `n_extract` 里的
`state["query"]` 换成 `state["requirement"]` 即可。

## 提示词保真度

四段 LLM 提示词 + 模板转换 Jinja 模板均**逐字节**取自 YAML，仅把
`{{#节点.变量#}}` 占位符改写为 `str.format` 字段名。由
`tests/test_prompts_match_dify.py` 自动校验（含节点/边的拓扑断言）。

## 新增的三个关卡（超出 Dify 原版）

原 Dify 工作流只有「`stderr` 为空」这一层退出条件，「能跑」即视为「成功」。
本实现补了三道**确定性**关卡，`verified` 字段只在三道全过时为 `True`：

| 关卡 | 位置 | 依据 | 失败处理 |
|------|------|------|----------|
| ④b 参数物理预检 | `extract → param_check → generate` | `physics.py`（每波长点数 / Nyquist / 时长 / PML / 源位置） | 回退 `extract` 重试（≤`PARAM_CHECK_MAX_ROUNDS`）；无 `dx` 时反算上限注入提示词 |
| ⑤b 静态规则检查 | `generate → static_check → run_code` | `static_check.py`（8 条 AST 规则，源自知识库黑名单） | 直接进 `fix_code`（**不浪费一次执行**） |
| ⑥b 语义数值门 | `run_code → semantic_gate → finalize` | `semantic.py`（`__JWAVE_SELFCHECK__` 自检行 + 数值判据） | 带原因进 `fix_code` |

与之配套的循环形态也变了（`fix_code` 现在回到 `static_check` 而不是直接 `run_code`）：

```
generate → static_check ──问题──► fix_code ─┐
              │通过                          │
              ▼                              │
          run_code ──运行报错──────────────► │
              │运行成功                      │
              ▼                              │
        semantic_gate ──语义不达标──────────►┘
              │通过
              ▼
          finalize（verified=True）
```

`iterations` 仍只统计**真实执行次数**，所以静态关卡拦下的代码不会消耗执行额度。
