# AcouAgent · 开发规划

> 版本 v1.0 | 2026-08-08 | 一人公司 + AI 辅助模式

---

## 目录

- [0. 阅读指南](#0-阅读指南)
- [1. 开发模式](#1-开发模式)
- [2. 阶段总览](#2-阶段总览)
- [3. 阶段一：基底稳定](#3-阶段一基底稳定-week-1-2)
- [4. 阶段二：智能体闭环](#4-阶段二智能体闭环-week-3-5)
- [5. 阶段三：产品交付](#5-阶段三产品交付-week-6-8)
- [6. 并行任务调度规则](#6-并行任务调度规则)
- [7. 每日工作流](#7-每日工作流)
- [8. 阶段门禁检查清单](#8-阶段门禁检查清单)

---

## 0. 阅读指南

### 这份文档给谁看

| 读者 | 怎么读 |
|------|--------|
| **AI Agent（主要读者）** | 按阶段索引找到当前任务，读完"Agent 上下文"块直接执行 |
| **你（项目 owner）** | 看阶段总览了解进度，看门禁清单决定是否进入下一阶段 |

### 与其他文档的关系

```
PRD.md          → "要做什么" （产品愿景）
ARCHITECTURE.md → "怎么设计" （技术方案）
本文件           → "按什么顺序做"（开发规划）
AGENTS.md       → "现在做什么"（当前任务队列，每次会话更新）
CHANGELOG.md    → "做了什么" （每次会话追加）
```

### 每条任务的标准格式

每条任务包含 Agent 可直接消费的完整上下文：

```
### 任务编号 · 任务名
| 属性 | 值 |
|------|-----|
| 输入 | 依赖的上游产出 |
| 输出 | 交付物清单 |
| 文件 | 要创建/修改的精确文件路径 |
| 验证 | Agent 可自己执行的验证命令 |
| 完成标准 | 布尔条件 |
```

---

## 1. 开发模式

### 1.1 核心原则

**一个人 + 一个 AI Agent 编队 = 一个开发团队。**

AI 不只是一个写代码的工具——它是你的开发团队。每次开发会话，你就是 Tech Lead：分配任务、审查产出、决定合并。AI Agent 是并行工作的工程师。

### 1.2 三条铁律

1. **一次只做一个阶段。** 阶段之间有硬门禁，前一阶段不达标准不进入下一阶段。
2. **能并行就并行。** 一个阶段内，无依赖的任务同时启动多个 Agent。
3. **每次会话结束必须更新状态。** CHANGELOG.md 追加记录，AGENTS.md 更新任务状态。下一个 Agent 才能接上。

### 1.3 Git 纪律

```
每次会话开始: git log --oneline -3   # 确认当前状态
每个任务完成: git add <files> && git commit -m "T-XXX: <变更摘要>"
每次会话结束: git push (如有远程)
出问题回退:   git checkout <commit> -- <file>  # 单文件回退
              git reset --hard <commit>         # 全量回退（慎用）
```

### 1.4 你的角色

| 角色 | 你做什么 | Agent 做什么 |
|------|----------|-------------|
| Tech Lead | 审查 Agent 产出、决定是否合并、运行最终验证 | 执行具体任务 |
| Product Owner | 确认功能符合预期、决定阶段门禁 | 按规格实现 |
| QA | 跑端到端测试、记录 bug | 写单元测试、修复 bug |

---

## 2. 阶段总览

```
                    现在
                     │
    ┌────────────────┼────────────────┐
    │                │                │
    ▼                ▼                ▼
阶段一 (Week 1-2)  阶段二 (Week 3-5)  阶段三 (Week 6-8)
  基底稳定           智能体闭环         产品交付
    │                │                │
    │ 成功率 76→90%   │ 对话界面+可视化  │ 开源发布
    │ Sources 修复    │ 迭代循环+记忆   │ 用户验证
    │ Prompt 强化     │ 结果分析+解释   │ 文档完善
    │ 参数校验        │                │
    │                │                │
    └───────┬────────┘───────┬────────┘
            │                │
        门禁: 50次≥90%   门禁: 20次多轮≥85%
```

### 阶段依赖

```
阶段一 ────→ 阶段二 ────→ 阶段三
  │              │              │
  │ 阻塞阶段二    │ 阻塞阶段三    │ 最终交付
  │ 必须完成      │ 必须完成      │
```

---

## 3. 阶段一：基底稳定（Week 1-2）

**目标**：成功率从 76% 提升到 90%+，修复 Sources 全零。**用户不可见变化，但这是所有后续工作的地基。**

### 3.1 任务清单

```
T-001 [P0] 排查 Sources 全零 ────── 无依赖 ────→ T-004
T-002 [P0] Prompt 强化 ──────────── 无依赖 ────→ T-004
T-003 [P0] 参数校验工具 ─────────── 无依赖 ────→ T-005
                                                    │
T-004 [P0] 知识库重索引 ─────────── T-001,T-002 ───┤
T-005 [P0] 工作流更新（+校验节点）─ T-003 ────────→ T-006
                                                    │
T-006 [P0] 50 次端到端测试 ──────── T-001~T-005 ──→ 门禁
```

### T-001 · 排查并修复 Sources 全零

| 属性 | 值 |
|------|-----|
| 输入 | 测试记忆 [[test-results-2025-08-07]]、API 记忆 [[jwave-api-gotchas]] |
| 输出 | `docs/SOURCES_FIX.md`（根因报告），可能有 `server_safe.py` 或知识库的修补 |
| 文件 | 只读：jwave 源码（executor 容器内）。可写：`docs/SOURCES_FIX.md` |
| 可用 Agent | 1 个（纯调研，不需要并行） |
| 验证 | `docker exec jwave-executor /opt/jwave/bin/python -c "..."` 执行 Sources 代码，max_pressure > 0 |
| 完成标准 | Sources 代码在 executor 中执行后压力场非零 |

**Agent 上下文**：
- jwave 0.2.1，容器 `jwave-executor`，Python `/opt/jwave/bin/python`
- 已知 Sources 正确签名: `Sources(positions, signals, dt, domain)` 4 个位置参数
- p0 方式已验证有效（600 Pa），Sources 方式 exit_code=0 但 max_pressure=0
- 排查路径: 读 Sources 源码 → 读 simulate_wave_propagation 源码 → 追踪 source term 注入点 → 对比 p0 路径

### T-002 · Prompt 强化

| 属性 | 值 |
|------|-----|
| 输入 | API 记忆 [[jwave-api-gotchas]]、当前 Prompt（Dify 工作流 + server_safe.py） |
| 输出 | 更新后的 `server_safe.py`（纠错 Prompt）、Dify 工作流（代码生成 Prompt）、新版知识库 md |
| 文件 | `server_safe.py`, Dify 工作流 graph, `/tmp/new_kb.md` |
| 可用 Agent | 2 个并行（一个改 server_safe.py，一个改 Dify 工作流） |
| 验证 | 代码生成不含禁止 API（grep 检查），纠错 Prompt 含错误速查表 |
| 完成标准 | Prompt 更新 + 知识库文档更新完毕 |

**Agent 上下文**：
- 纠错 Prompt（server_safe.py `_llm_fix_code()`）：注入 jwave 错误速查表
- 代码生成 Prompt（Dify 工作流节点）：嵌入正确 API + 禁止 API 黑名单
- 禁止 API: `p0.shape`, `time_axis.t`, `FourierSeries.from_array()`, `Sources(domain=..., source=...)`
- 知识库需新增 2 个完整代码示例（点源 + 初始压力）

### T-003 · 参数校验 MCP 工具

| 属性 | 值 |
|------|-----|
| 输入 | PRD 附录 B.5、ARCHITECTURE.md 第 4.1.3 节 |
| 输出 | `server_safe.py` 中新增 `validate_simulation_params` 函数（~180 行） |
| 文件 | `server_safe.py` |
| 可用 Agent | 1 个 |
| 验证 | 5 种边界条件测试：合法参数/ Nyquist 超标/ CFL 超标/ N<32/ PML<10 |
| 完成标准 | 工具在 MCP 中注册成功，所有校验规则正确触发 |

**Agent 上下文**：
- 在 `run_jwave_code_with_retry` 函数之后、`if __name__ == "__main__"` 之前插入
- 7 项校验：必填字段、Nyquist（λ/4）、CFL（≤0.3）、网格（[32,1024]）、PML（<10 warning）、MHz 分辨率（<0.5mm）、时间-距离匹配
- 所有数值比较使用 1.001 倍浮点容差
- 返回格式: `{"valid": bool, "errors": [...], "warnings": [...]}`

### T-004 · 知识库部署与重索引

| 属性 | 值 |
|------|-----|
| 输入 | T-001 找到的 API 问题（如有）+ T-002 生成的新 kb 文件 |
| 输出 | Dify 知识库已重索引，segments ≥ 10 |
| 文件 | `/tmp/new_kb.md` → Dify 容器内 → PostgreSQL |
| 可用 Agent | 1 个 |
| 验证 | `docker exec docker-db_postgres-1 psql -U postgres -d dify -c "SELECT COUNT(*) FROM document_segments WHERE document_id = '1280a56c-...';"` |
| 完成标准 | 知识库状态=completed，segments > 0 |

**Agent 上下文**：
- 流程: 替换文件 → 更新 upload_files.size → 重置 indexing_status='waiting' → 删旧 segments → 触发 Celery 索引 → 等 30s 验证
- 参照记忆 [[kb-edit-process]]

### T-005 · Dify 工作流更新

| 属性 | 值 |
|------|-----|
| 输入 | T-003（校验工具）, T-004（新知识库） |
| 输出 | Dify draft 工作流更新：8 节点 → 10 节点（+参数校验 +结果审查） |
| 文件 | Dify workflows 表 graph JSON（App ID: 0592503e-...） |
| 可用 Agent | 1 个 |
| 验证 | 在 Dify 中执行一次仿真，流程经过参数校验节点 |
| 完成标准 | 工作流包含参数校验节点，不合理参数被拦截 |

**Agent 上下文**：
- 读取 draft 工作流 JSON → 在参数提取和代码生成之间插入校验节点 → 写回
- 修改后必须重启: `docker restart docker-api-1 docker-worker-1`
- 参照记忆 [[dify-workflow-jwave]]

### T-006 · 50 次端到端回归测试

| 属性 | 值 |
|------|-----|
| 输入 | T-001~T-005 全部完成 |
| 输出 | `docs/test_report_phase1.md` — 50 次测试明细 + 成功率统计 |
| 文件 | 无代码变更，仅测试 |
| 可用 Agent | 1 个（串行执行，每次测试约 30-60s） |
| 验证 | 成功率 ≥ 90%（≥45/50） |
| 完成标准 | 报告文件生成，成功率达标 |

**测试用例分布**：
- 10 次：2D 均质点源（基准场景）
- 10 次：2D 均质 p0（对比场景）
- 10 次：2D 异质介质（囊肿/骨骼）
- 10 次：带传感器记录波形
- 10 次：边界情况（极低频率、极小网格）

### 3.2 阶段一 Agent 调度图

```
会话 1: 并行 3 Agent
  ├── Agent A: T-001 (Sources 排查)
  ├── Agent B: T-002 (Prompt 强化)
  └── Agent C: T-003 (参数校验工具)

会话 2: 并行 2 Agent (依赖会话 1 产出)
  ├── Agent D: T-004 (知识库部署)
  └── Agent E: T-005 (工作流更新)

会话 3: 1 Agent
  └── Agent F: T-006 (50 次测试)

会话 4: 你亲自
  └── 审查测试报告 → 决定是否进入阶段二
```

### 3.3 阶段一门禁

必须全部通过才能进入阶段二：

- [x] T-001 Sources 压力场非零
- [x] T-002 Prompt 和知识库已更新
- [x] T-003 validate_simulation_params 工具已上线
- [x] T-004 知识库已重索引
- [x] T-005 工作流含校验节点
- [x] T-006 50 次测试成功率 ≥ 90%（实测 96%, 48/50, 2026-08-09）
- [x] `git tag phase-1-complete` 已打标签（2026-08-17 补打）

> ⚠️ **门禁口径说明（2026-08-17 校准）**：T-006 的 96% 是**执行级宽松判定**——成功 = `exit_code==0` 且未超时且 `max_pressure` 缺失或 >0（见 `run_50_tests_new.py` L152-156）。它**不代表物理正确性**（全零结果、量级异常均可能被判"成功"）。物理正确性由**阶段二 VAL-1 验证基准集**保障（解析解/论文对照，误差 <1%）。阶段一关闭仅代表"链路稳定跑通"，不代表"结果可信"。

---

## 4. 阶段二：智能体闭环（Week 3-5）

**目标**：先建立物理验证基准，再构建结果可信度闭环（验证→审查→纠偏），最后封装为可对话的 Web 产品。**用户看到的不再是"跑通"，而是"对标物理事实的可信结果"。**

### 4.1 任务清单

```
VAL-1 [P0] 验证基准集 ──── 无依赖 ────→ T-007   ← 新增：质量验证的地基
T-007 [P1] 结果分析 MCP 工具 ─ VAL-1 ──→ T-008
T-008 [P1] 结果解释 + 审查节点 ─ T-007 ──→ T-009
T-009 [P1] 迭代循环（工作流改造）─ T-008 ──→ T-010
                                                    │
T-010 [P1] Gradio Web 前端 ──── T-009 ───────→ T-011
                                                    │
T-011 [P1] 多轮对话记忆 ─────── T-010 ───────→ T-012
                                                    │
T-012 [P1] 20 次多轮仿真测试 ── T-007~T-011 ──→ 门禁
```

### VAL-1 · 建立仿真验证基准集

| 属性 | 值 |
|------|-----|
| 优先级 | P0（阶段二第一个任务，T-007 前置） |
| 输入 | jwave 0.2.1 正确 API（kb_jwave_reference.md）、解析解公式、jwave 原论文 |
| 输出 | `docs/VALIDATION_BASELINE.md` + executor 可一键重跑的基准脚本 |
| 文件 | 新建 `executor/validation_baseline.py`、`docs/VALIDATION_BASELINE.md` |
| 可用 Agent | 1 个 |
| 验证 | 每个用例：解析/论文理论值 vs 仿真实测，误差 <1% 判定 |
| 完成标准 | ≥3 个用例误差 <1%，基准脚本可在 executor 一键重跑 |

**Agent 上下文**：
- 目的：为 T-007 的 `verdict` 提供**物理基准**（否则只能做"内部自洽"，无法判断结果是否正确）
- 用例设计（解析解优先，无需外网）：
  1. **平面波无损耗传播**：均匀介质平面波 → 振幅应守恒，`max_pressure ≈ 初始激励`（解析解）
  2. **球面波 1/r 衰减**：点源在均匀介质 → 压力随距离按 1/r 衰减（解析解）
  3. **平界面反射/透射系数**：两种介质平面界面 → 反射/透射系数有闭式公式（声阻抗法），对比理论值
  4. **jwave 原论文数值算例复现**（如可得）：复现论文中的声场算例，对比论文数据
  5. **k-Wave 标准算例对照**（可选）：同一算例与 k-Wave 参考解对比
- 每个用例输出：场景定义 → 理论值公式 → 实测值 → 误差 → 判定
- 误差基准：误差 <1% 判定通过（对应 PRD D.23）；网格分辨率不足导致的误差应在文档中说明收敛趋势

### T-007 · analyze_simulation_result MCP 工具

| 属性 | 值 |
|------|-----|
| 输入 | VAL-1（验证基准集）、仿真 stdout（含压力场数据）、ARCHITECTURE.md 第 4.1.4 节 |
| 输出 | `server_safe.py` 新增 `analyze_simulation_result` 函数，executor 中生成 PNG |
| 文件 | `server_safe.py`，可能需要 `executor/Dockerfile`（安装 matplotlib） |
| 可用 Agent | 1 个 |
| 验证 | 执行一次仿真后，工具返回 heatmap_base64 非空、max_pressure 正确；**verdict 对照 VAL-1 基准判定** |
| 完成标准 | 每次成功仿真自动生成热力图 PNG + 物理量摘要；**≥3 个基准用例误差 <1%** |

**Agent 上下文**：
- 输入: stdout_text, stderr_text, exit_code, params_json
- 输出: {has_signal, max_pressure, rms_pressure, field_shape, heatmap_base64, waveform_base64, verdict, summary}
- 需要代码生成节点额外输出压力场 JSON 数据到 stdout
- 如果 matplotlib 不可用，生成 ASCII 热力图降级

### T-008 · 结果解释 + 审查 LLM 节点

| 属性 | 值 |
|------|-----|
| 输入 | T-007 输出格式、Dify 工作流 |
| 输出 | Dify 工作流新增 2 个 LLM 节点（审查 + 解释） |
| 文件 | Dify 工作流 graph JSON |
| 可用 Agent | 1 个 |
| 验证 | 仿真完成后自动输出自然语言解读（≥3 句） |
| 完成标准 | 审查节点能判断 pass/retry/fail，解释节点含物理意义 |

**Agent 上下文**：
- 审查节点 Prompt: 判断压力场是否正常（全零？量级合理？传播距离匹配？），输出 {"verdict": "pass"|"retry"|"fail", "suggestion": "..."}
- 解释节点 Prompt: 输入分析摘要 → 输出 3+ 句自然语言，含数值和物理直觉
- 审查 retry → 回到参数提取节点，最多 3 次

### T-009 · 迭代循环（工作流改造）

| 属性 | 值 |
|------|-----|
| 输入 | T-003（校验触发修正）、T-008（审查触发重试） |
| 输出 | 工作流包含两条反馈回路：校验失败→参数提取、审查 retry→参数提取 |
| 文件 | Dify 工作流 graph JSON |
| 可用 Agent | 1 个 |
| 验证 | 注入全零结果 → 自动回到参数提取 → 最多 3 次后放弃 |
| 完成标准 | 迭代循环正确触发和终止 |

**Agent 上下文**：
- 工作流从 10 节点变为 ~13 节点
- 条件分支: 校验 pass → 代码生成；校验 fail → 参数提取（带修正建议）
- 条件分支: 审查 pass → 结果解释；审查 retry → 参数提取（iteration<3）；审查 fail → 错误输出
- 用 Dify conversation variable `iteration_count` 防止死循环

### T-010 · Gradio Web 前端

| 属性 | 值 |
|------|-----|
| 输入 | Dify Chat API、T-007（图片生成） |
| 输出 | `frontend/app.py`（~200 行）、`frontend/Dockerfile`、`frontend/requirements.txt` |
| 文件 | 新建 `frontend/` 目录 |
| 可用 Agent | 1 个 |
| 验证 | 浏览器打开 `http://192.168.30.200:7860`，可对话并看到图片 |
| 完成标准 | 聊天界面可用，对话含文字+图片，对话历史可持续 |

**Agent 上下文**：
```python
# 核心骨架
import gradio as gr
import httpx

DIFY_API_URL = "http://docker-api-1:5001/v1"
DIFY_API_KEY = os.environ["DIFY_API_KEY"]

async def chat(message, history):
    # POST Dify Chat API (streaming)
    # SSE 解析 → yield 逐 token 更新
    # 检测 base64 图片 → 嵌入 <img> 标签
    ...
```
- 需要 Dify 的 App API Key（不是 MCP token）
- 流式输出用 SSE（Server-Sent Events）
- 图片 base64 → Markdown `![](data:image/png;base64,...)` 嵌入气泡

### T-011 · 多轮对话上下文记忆

| 属性 | 值 |
|------|-----|
| 输入 | Dify conversation variables、T-005（工作流） |
| 输出 | 工作流中参数提取节点可读取上轮参数 |
| 文件 | Dify 工作流 graph |
| 可用 Agent | 1 个 |
| 验证 | "5MHz 在软组织中" → 执行 → "改成 3MHz" → 仅 frequency 改变 |
| 完成标准 | 增量修改参数时，其他参数保持不变 |

**Agent 上下文**：
- 新增 conversation variables: `last_params`, `last_summary`
- 参数提取节点 Prompt 注入: "上次仿真参数: {{#conversation.last_params#}}。若用户只要求修改某参数，基于上次参数仅改该值。"
- 每次成功仿真后，变量赋值节点更新这两个变量

### T-012 · 20 次多轮仿真集成测试

| 属性 | 值 |
|------|-----|
| 输入 | T-007~T-011 全部完成 |
| 输出 | `docs/test_report_phase2.md` |
| 文件 | 无代码变更 |
| 可用 Agent | 1 个 |
| 验证 | 上下文正确率 ≥ 85%（17/20） |
| 完成标准 | 报告文件生成，多轮对话和可视化正常 |

### 4.2 阶段二 Agent 调度图

```
会话 5: 并行 3 Agent
  ├── Agent G: T-007 (结果分析工具)
  ├── Agent H: T-008 (审查+解释节点)
  └── Agent I: T-009 (迭代循环)

会话 6: 并行 2 Agent
  ├── Agent J: T-010 (Gradio 前端)
  └── Agent K: T-011 (多轮记忆)

会话 7: 1 Agent
  └── Agent L: T-012 (20 次多轮测试)

会话 8: 你亲自
  └── 试用前端 → 审查测试报告 → 决定是否进入阶段三
```

### 4.3 阶段二门禁

- [x] **VAL-1 验证基准集完成：≥3 个用例（解析解/论文）误差 <1%**（2026-08-18：3/3 PASS，用例1 0.0002%、用例2 0.80%、用例3 R/T 0.003%/0.002%，见 `docs/VALIDATION_BASELINE.md`）
- [x] T-007 结果分析工具上线，每次仿真出热力图，**verdict 可对标 VAL-1 基准**（2026-08-18：`analysis.py` 已实现并 VM 端到端验证 verdict/热力图；工作流内接入随 T-008）
- [x] T-008 审查节点能判断 pass/retry/fail（2026-08-18：工作流 13 节点已发布，审查+解释节点上线，真实运行输出含物理解读；retry 循环属 T-009）
- [ ] T-009 迭代循环 ≤3 次正确终止
- [ ] T-010 Gradio 前端可访问，对话+图片正常
- [ ] T-011 增量修改参数上下文正确率 ≥ 85%
- [ ] T-012 20 次多轮测试通过
- [ ] `git tag phase-2-complete` 已打标签

---

## 5. 阶段三：产品交付（Week 6-8）

**目标**：包装为可发布的产品。文档完善、测试覆盖、用户验证。

### 5.1 任务清单

```
T-013 [P2] 知识库扩展（5 文档）─── 无依赖 ────→ T-016
T-014 [P2] Dashboard 增强 ─────── 无依赖 ────→ T-016
T-015 [P2] 仿真方案推荐 ───────── 无依赖 ────→ T-016
                                                    │
T-016 [P2] 用户验收测试 ───────── T-013~T-015 ──→ 门禁
T-017 [P2] 文档 + 开源准备 ────── T-016 ────────→ 门禁
```

### T-013 · 知识库扩展

| 属性 | 值 |
|------|-----|
| 输入 | PRD 附录 B.1 |
| 输出 | 5 个知识库 markdown 文件，全部已索引 |
| 文件 | `/tmp/kb_*.md` → Dify 容器 → PostgreSQL |
| 可用 Agent | 1 个（5 个文件可合并为一个 Agent 串行处理） |
| 验证 | 知识库 segments 总数 ≥ 30 |
| 完成标准 | 5 个文档全部状态=completed |

### T-014 · Dashboard 增强

| 属性 | 值 |
|------|-----|
| 输入 | `dashboard.py` |
| 输出 | 新增仿真回放、参数对比、失败分析功能 |
| 文件 | `dashboard.py` |
| 可用 Agent | 1 个 |
| 验证 | Dashboard 可见新增统计面板 |
| 完成标准 | 看板可对比两次仿真的参数和结果 |

### T-015 · 仿真方案自主推荐

| 属性 | 值 |
|------|-----|
| 输入 | PRD 第 5.3.2 节 |
| 输出 | 增强需求分析 Prompt + 知识库参数表 |
| 文件 | Dify 工作流 + 知识库 |
| 可用 Agent | 1 个 |
| 验证 | 50% 以上的仿真请求中，智能体给出 ≥2 条有意义的参数建议 |
| 完成标准 | 方案推荐覆盖 5 种以上常见场景 |

### T-016 · 5 人用户验收测试

| 属性 | 值 |
|------|-----|
| 输入 | 阶段三所有前置任务 |
| 输出 | `docs/uat_report.md` |
| 可用 Agent | 无（你需要亲自找人测试） |
| 验证 | 满意度 ≥ 4/5，10 种场景全覆盖 |
| 完成标准 | 测试报告完成，阻塞性 bug=0 |

### T-017 · 文档 + 开源准备

| 属性 | 值 |
|------|-----|
| 输入 | 全部开发完成 |
| 输出 | README.md 重写、CONTRIBUTING.md、LICENSE、部署文档 |
| 文件 | `README.md`, `docs/DEPLOY.md`, `LICENSE` |
| 可用 Agent | 1 个 |
| 验证 | 新开发者按 README 能在 30 分钟内部署并跑通首次仿真 |
| 完成标准 | 所有文档齐备，GitHub 仓库 ready |

### 5.2 阶段三门禁

- [ ] T-013~T-015 全部完成
- [ ] T-016 用户满意度 ≥ 4/5
- [ ] T-017 新开发者 30 分钟上手验证通过
- [ ] `git tag v1.0.0` 已打标签

---

## 6. 并行任务调度规则

### 6.1 何时可以并行

```
可以并行:
  ✅ 两个任务修改不同的文件
  ✅ 两个任务修改同一文件的不同函数（且不相邻）
  ✅ 任务是纯调研（不改文件）

不能并行:
  ❌ 两个任务修改同一文件的同一区域
  ❌ 任务 B 的输入依赖任务 A 的产出
  ❌ 两个任务都需要重启同一个 Docker 容器
```

### 6.2 并行冲突解决

如果两个并行 Agent 都改了同一文件（如 T-002 和 T-003 都改 server_safe.py），合并策略：

```bash
# 1. 先合第一个
cp worktree-1/server_safe.py <项目目录>/
git add -A && git commit -m "合并 Agent A 的修改"

# 2. 手动合第二个（不能用 cp，会覆盖）
# 用 git diff worktree-2/server_safe.py 查看差异，手动 Edit
```

### 6.3 最大并行数

| 场景 | 最大 Agent 数 |
|------|-------------|
| 改不同文件 | 3 |
| 改同一文件不同区域 | 2 |
| 纯调研（不改文件） | 3 |
| 涉及 Docker 操作 | 1（Docker 操作不是线程安全的） |

---

## 7. 每日工作流

### 7.1 会话启动（你或 Agent 执行）

```markdown
1. [ ] 确认环境: docker ps | grep -E "dify-mcp|jwave-executor"
2. [ ] 确认 MCP: curl http://192.168.30.200:8001/health
3. [ ] 读 CHANGELOG.md 了解上次进度
4. [ ] 读 AGENTS.md 找到下一个 TODO 任务
5. [ ] 决定本次会话要完成哪几个任务
```

### 7.2 会话中（Agent 执行）

```markdown
6. [ ] 对于每个任务: 读任务上下文 → 执行 → 自验证
7. [ ] 任务完成: git commit 单任务
8. [ ] 任务失败: 记录失败原因到 CHANGELOG.md
```

### 7.3 会话结束（Agent 执行）

```markdown
9.  [ ] 更新 CHANGELOG.md: 本次完成了什么
10. [ ] 更新 AGENTS.md: 任务状态变更（[TODO] → [DONE]）
11. [ ] git log --oneline -3 确认状态清晰
12. [ ] 如有需要部署: docker compose up -d --build
```

---

## 8. 阶段门禁检查清单

### 阶段一门禁

- [ ] Sources 点源压力场非零
- [ ] validate_simulation_params 工具上线（6 个 MCP 工具）
- [ ] 纠错 Prompt 含 jwave 错误速查表
- [ ] 知识库已重索引（segments ≥ 10）
- [ ] 工作流含参数校验节点
- [ ] 50 次端到端测试成功率 ≥ 90%
- [ ] `git tag phase-1-complete`

### 阶段二门禁

- [ ] VAL-1 验证基准集 ≥3 用例误差 <1%
- [ ] analyze_simulation_result 工具上线（verdict 对标基准）
- [ ] 每次仿真自动生成热力图
- [ ] 审查节点能判断 pass/retry/fail
- [ ] 迭代循环 ≤3 次终止
- [ ] Gradio 前端可对话 + 显示图片
- [ ] 多轮对话上下文正确率 ≥ 85%
- [ ] 20 次多轮测试通过
- [ ] `git tag phase-2-complete`

### 阶段三门禁

- [ ] 知识库 5 个文档全部上线
- [ ] 10 种仿真场景全覆盖
- [ ] 5 人用户满意度 ≥ 4/5
- [ ] 新开发者 30 分钟上手
- [ ] README + 部署文档完整
- [ ] `git tag v1.0.0`

---

## 附录：进度追踪（每次会话后更新）

### 当前阶段：阶段二（智能体闭环，进行中）｜阶段一 ✅（门禁通过 2026-08-09，tag 收尾 2026-08-17）

| 任务 | 状态 | 完成日期 | Commit |
|------|------|----------|--------|
| T-001 Sources 全零 | ✅ 完成 | 2026-08-08 | 9c1a7e6 |
| T-002 Prompt 强化 | ✅ 完成 | 2026-08-08 | 9c449a1 |
| T-003 参数校验工具 | ✅ 完成 | 2026-08-08 | 9c449a1 |
| T-004 知识库重索引 | ✅ 完成 | 2026-08-08 | 随 T-002 |
| T-005 工作流更新 | ✅ 完成 | 2026-08-08 | - |
| T-006 50 次测试 | ✅ 完成 (96%, 48/50) | 2026-08-09 | fecb882, 3faaa39 |

| 阶段二任务 | 状态 | 完成日期 | 交付物 |
|------|------|----------|--------|
| VAL-1 验证基准集 | ✅ 完成 (3/3 PASS) | 2026-08-18 | `executor/validation_baseline.py` + `docs/VALIDATION_BASELINE.md` |
| T-007 结果分析工具 | ✅ 完成（工具已上线，工作流接入随 T-008） | 2026-08-18 | `analysis.py`（analyze_simulation_result） |
| T-008 审查+解释节点 | ✅ 完成（工作流 13 节点已发布上线） | 2026-08-18 | `_build_graph.py` + 工作流 graph（备份在 `docs/dify_workflow_backup/`） |
| T-009 迭代循环 | ⬜ TODO | - | - |

> **阶段一已关闭**（2026-08-17 补打 `phase-1-complete` tag）。剩余质量遗留：P2「2D均质初始压力」成功率 80%（50 次测试中 2 失败），建议在阶段二开发前或并行修复。
> **阶段二进行中：VAL-1 ✅、T-007 ✅、T-008 ✅（2026-08-18）→ 下个任务 T-009（迭代循环，审查 retry 回参数提取 ≤3 次）**

### 图例

```
⬜ TODO     🔄 运行中     ✅ 完成     ❌ 阻塞
```
