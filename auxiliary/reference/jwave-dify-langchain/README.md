# jwave 仿真工作流 — Dify → LangChain/LangGraph

把 Dify 工作流应用「仿真」（`dify_workflow/仿真.yml`）实现为 LangChain / LangGraph：
自然语言声学仿真需求 → 检索知识库 → 生成 jwave 代码 → 执行并自我纠错 → 输出可用代码。

```
① 需求分析 → ② 知识检索 → ③ 模板转换 → ④ 参数提取 → 参数物理预检 → ⑤ 代码生成
                                                                        ↓
       ⑧ 输出 ←── 语义数值门 ←── ⑥ 执行 ←── 静态规则检查 ←──────────────┘
                        ↑                    │
                        └──── ⑦ 代码纠错 ←────┘   （循环 ≤ 10 轮）
```

节点、边与提示词的逐项对照见 [./docs/MAPPING.md](docs/MAPPING.md)。

## 安装

```bash
conda activate jw                          # 请替换为本机的任意 Python >= 3.10 环境
pip install -r requirements.txt            # 编排层：langchain / langgraph / openai / rich
pip install -r requirements-runtime.txt    # jwave 仿真运行时 + 可选执行后端
```

## 配置

配置全部来自环境变量，`.env` 可选（其值不会覆盖已存在的环境变量）：

```bash
cp .env.example .env
```

至少提供 API Key 与端点。只设 `DEEPSEEK_API_KEY` 时会自动指向
`https://api.deepseek.com/v1`：

```bash
export DEEPSEEK_API_KEY=sk-...
# 或者使用其它 OpenAI 兼容服务
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.deepseek.com/v1
```

常用变量（完整列表见 `.env.example`）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` | — | 必填，二者取其一 |
| `OPENAI_BASE_URL` | OpenAI 官方 | 任意 OpenAI 兼容端点 |
| `ANALYST_MODEL` | `deepseek-flash` | 需求分析 / 参数提取 |
| `CODER_MODEL` | `deepseek-flash` | 代码生成 / 代码纠错 |
| `KB_PATH` | `kb/jwave_kb_organized.md` | 知识库 markdown |
| `RETRIEVAL_BACKEND` | `bm25` | `bm25`（离线）/ `openai`（embedding 向量检索） |
| `RETRIEVAL_TOP_K` | `4` | 检索命中数 |
| `EXECUTOR_BACKEND` | `subprocess` | `subprocess` / `jupyter` / `mcp` / `auto` |
| `EXEC_PYTHON` | 当前解释器 | 执行生成代码的解释器 |
| `EXEC_TIMEOUT` | `600` | 单次执行超时（秒） |
| `LOOP_MAX_ITERATIONS` | `10` | 执行 / 纠错最大轮数 |

## 使用

### 命令行

```bash
python -m jwave_flow "生成一个 128x128 的二维时域声学仿真，声速 1500，5MHz 点源"
jwave-flow "..."            # 等价的入口命令
```

| 选项 | 说明 |
|------|------|
| `--out FILE` | 把最终代码写入文件 |
| `--json` | 输出完整状态（`verified` / `semantic_issues` / `stdout` / `trace`） |
| `--query-file FILE` | 从文件读取需求 |
| `--kb FILE` `--top-k N` `--retrieval {bm25,openai}` | 覆盖检索配置 |
| `--backend {subprocess,jupyter,mcp,auto}` | 覆盖执行后端 |
| `--model NAME` | 同时覆盖 analyst / coder 模型 |
| `--max-iterations N` | 循环上限 |
| `--quiet` | 不打印过程日志 |
| `--check-api` | 只发一个最小请求，验证 API 与网络可达 |
| `--tui` / `--no-tui` | 强制进入 / 禁用交互界面 |

### 交互式界面

不带需求参数、且 stdin 是终端时自动进入；也可显式启动：

```bash
python -m jwave_flow --tui
jwave-tui
```

菜单为：新建任务 / 运行配置 / 知识库速览 / 历史记录 / 使用说明。
运行中实时刷新各节点状态、关卡计数与日志，结束后给出三道关结论、自检数据与最终代码。

需求输入框支持：`:help`、`:settings`（配置编辑器，写回 `.env`）、`:kb`、`:history`、
`:preset`（内置示例需求）、`@file.txt`（从文件读取需求）。
每次运行追加一条记录到 `run/history.jsonl`。

交互界面依赖 `rich` 与 `prompt_toolkit`；两者缺失时非交互模式仍可正常使用。

### 代码里调用

```python
from jwave_flow import SimulationWorkflow, Settings

with SimulationWorkflow(Settings.from_env()) as wf:
    result = wf.invoke("做个二维时域仿真")
    print(result["text"])       # 最终代码
    print(result["verified"])   # 是否通过语义校验
```

## 语义校验

「执行不报错」不等于「结果正确」，因此流水线在生成与运行前后加了三道确定性检查；
全部通过时 `result["verified"]` 才为 `True`，否则输出会标注「未通过语义校验」，
且失败原因会回灌给「代码纠错」节点。

| 关卡 | 时机 | 检查内容 |
|------|------|----------|
| 参数物理预检 | 生成代码之前 | 每波长网格点数、Nyquist 采样、仿真时长、PML 厚度、源位置。不合格则不进入代码生成，回退重试参数提取（≤2 轮）；参数中没有 `dx` 时反算合规上限并注入提示词 |
| 静态规则检查 | 运行之前 | 8 条 AST 规则拦截已知的错误用法：`tone_burst(dt,…)`、对压力场的二次转换、浮点 `positions`、`Sources` 关键字参数、`signals`/`positions` 传 list 等。命中的代码一次都不会被执行 |
| 语义数值门 | 运行之后 | 要求代码打印 `__JWAVE_SELFCHECK__{...}` 自检行，校验有限性、`|p|max` 非零与量级、形状、频率是否与需求一致 |

```bash
# 单独关闭某一道（排查时用）
PARAM_CHECK=0 STATIC_CHECK=0 REQUIRE_SELFCHECK=0 python -m jwave_flow "..."
```

## 代码执行后端

原工作流依赖的 `RUN_PYTHON_CODE`（MCP 服务器 `python运行mcp`）不可用，改为可插拔执行器，
四者返回同一份契约（`stdout` / `stderr` / `results` / `outputs` / `new_files` / `execution_time`）：

| 后端 | 机制 | 依赖 |
|------|------|------|
| `subprocess`（默认） | 一次性执行完整脚本 | 无 |
| `jupyter` | 常驻 `ipykernel` | `ipykernel` |
| `mcp` | 启动 `python-mcp-server` 并走 stdio 调用 | `mcp`、`python-mcp-server` |
| `auto` | 先试 `jupyter`，失败降级 `subprocess` | — |

生成的代码以当前用户权限运行，仅有超时与独立工作目录隔离，**不是安全沙箱**。
执行器默认注入 `JAX_PLATFORMS=cpu`与 `MPLCONFIGDIR`
（否则 matplotlib 字体缓存会写 stderr，被循环误判为失败）。首次运行可先执行
`python tools/warm_env.py` 完成预热。

## 知识库

知识库为 `kb/jwave_kb_organized.md`，原始文件备份在 `kb/jwave_kb_organized.md.bak`，
修改清单见 `kb/FIXES.md`。

```bash
python tools/fix_kb.py            # 应用修正（幂等）
python tools/fix_kb.py --check    # 只报告
python tools/fix_kb.py --revert   # 回滚到原始知识库
```

## 目录结构

```
jwave-dify-langchain/
├── dify_workflow/仿真.yml      # 原始 Dify 工作流（只读参考）
├── jwave_flow/
│   ├── config.py               # 环境变量配置与端点解析
│   ├── prompts.py              # 从 YAML 逐字提取的提示词
│   ├── llm.py                  # OpenAI 兼容模型 + 结构化输出回退
│   ├── knowledge.py            # 知识库切分 + BM25 / embedding 检索
│   ├── executor.py             # subprocess / jupyter / mcp 执行器
│   ├── physics.py              # 参数物理预检
│   ├── static_check.py         # AST 静态规则检查
│   ├── semantic.py             # 输出契约与数值门
│   ├── state.py / graph.py     # LangGraph 状态与工作流图
│   ├── cli.py                  # 命令行入口
│   ├── tui.py / panels.py      # 交互式界面与渲染
│   ├── errors.py               # 异常归因（网络 / 鉴权 / 模型名 / 限流）
│   └── history.py              # run/history.jsonl 读写
├── kb/                         # 知识库、备份与修改记录
├── tools/                      # fix_kb.py / warm_env.py
├── docs/MAPPING.md             # Dify ↔ LangGraph 映射表
└── tests/
```

## 测试

```bash
python -m pytest tests -q
```

覆盖提示词与 YAML 的逐字保真、图拓扑、知识库检索、执行器契约、静态与语义规则，
以及用 stub LLM 和本地 mock OpenAI 服务跑通整张图；不需要 API Key。

## 排错

模型调用失败与工作流本身无关时，先单独验证连通性：

```bash
python -m jwave_flow --check-api
```

它会先检查 API Key 与端点是否属于同一服务商（例如 `DEEPSEEK_API_KEY` 配了 OpenAI 地址，
会直接指出而不是报成网络问题），再发一个最小请求。交互界面里等价操作是
「运行配置」→ 按 `t`。

* 节点异常不会以 traceback 收场：流程图会标出出错的节点并给出归因与建议；
  非交互模式输出同样的文案并返回退出码 `2`。
* 失败的运行同样写入 `run/history.jsonl`（含 `error` / `error_hints`）。
* 需要原始堆栈时用 `JWAVE_DEBUG=1 python -m jwave_flow ...`。

## 已知限制

* 执行器不是安全沙箱，请勿将不可信输入交给该工作流。
* `bm25` 是词法检索，不含 Dify 的 `qwen3-rerank` 重排；需要重排可用 `openai` embedding 后端或自行替换 vector store。
* 「需求分析」节点在原始 Dify 图中的输出未被下游引用，此处忠实保留（见 `docs/MAPPING.md`）。
* 若生成的代码长期无法自愈，多半是知识库与所装 jwave 版本仍有差异，可用 `--json` 查看 `stderr` 与 `trace`。
* 交互界面显示的「执行用时」是相邻节点事件的时间差，包含该节点内的 LLM 调用耗时，仅供观察节奏。
