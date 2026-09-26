# AcouAgent 技术优化与可信演进规划

> 版本：v2.0
> 日期：2026-09-27
> 状态：正式执行版
> 适用范围：AcouAgent / dify-mcp-server 及其 Dify 工作流、MCP 网关、jwave executor、Web 控制台和测试体系
> 替代关系：本文件完整替代原《开发规划》v1.0。原阶段一、阶段二作为已完成基线保留在 Git 历史中；原阶段三被本规划重新定义。

---

## 0. 执行摘要

AcouAgent 已完成从自然语言到声学仿真结果的基本闭环：Dify 负责任务编排，FastMCP 提供参数校验、执行、纠错和结果分析工具，jwave executor 在受限容器中运行代码，Web 端提供多轮对话和执行看板。历史验证显示，执行级成功率曾达到 96%，多轮上下文正确率达到 95%，VAL-1 的 5 类基准场景均达到 1% 以内误差。

下一阶段的核心目标不是继续堆叠页面、Prompt 或工作流节点，而是把系统从“能够自动运行”提升为“能够说明为什么可信、能够复用已验证经验、能够在证据不足时拒绝学习”。

本规划确定以下技术主线：

1. 先收敛 Git、运行容器、工作流和文档四个基线，消除部署漂移。
2. 用统一 `run_id` 串联需求、参数、代码、执行、分析、纠错和成本，建立可追溯证据链。
3. 将“执行成功”“数值有效”“参数合理”“场景物理正确”“参考基准通过”分级，停止把 `exit_code=0` 或当前 `verdict=normal` 当作物理正确。
4. 新增 SQLite 成功技能库，在代码生成前提供结构化检索；技能写入必须经过质量门控。
5. 先影子检索、后小流量注入，使用配对 A/B 测试证明技能库确实提高首次物理成功率并减少重试。
6. 保留 Dify、FastMCP 和 jwave executor，不引入 Open Interpreter、CloudPSS 或 Milvus；只有明确指标证明现有架构不足时才升级。

第一优先级交付物为：

- `skill_store.py`；
- MCP 工具 `search_simulation_skill`；
- 统一运行追踪 `run_id`；
- 场景级物理质量门控；
- Dify 参数提取后、代码生成前的技能检索节点；
- 可重复的技能检索 A/B 评测。

---

## 1. 规划依据与当前基线

### 1.1 依据文件

本规划综合以下证据形成：

| 依据 | 用途 |
|---|---|
| `README.md` | 当前入口、工具、部署与使用方式 |
| `docs/ARCHITECTURE.md` | 现有分层架构和接口边界 |
| `docs/PRD.md` | 产品目标、用户场景和非功能要求 |
| `docs/VALIDATION_BASELINE.md` | VAL-1 解析解/数值基准和误差口径 |
| `docs/TESTING.md` | 现有测试入口和验收方法 |
| `docs/CHANGELOG.md` | 已完成任务和历史验证记录 |
| `analysis.py`、`tools.py`、`cache_store.py`、`dashboard.py`、`portal.py` | 当前真实实现，而非文档推断 |
| 《智能体仿真项目优化方向》v1.5 | 清华论文、开源实现与本项目的映射分析 |
| 《基于大语言模型的电力仿真智能体及其技能库设计方法》 | 技能检索、执行反馈和成功轨迹沉淀的参考范式 |

参考工作的价值在于“技能库 + 检索 + 环境反馈 + 经验演进”的方法。其 FastAPI、Open Interpreter、Milvus 和 CloudPSS 只是特定实现，不作为本项目迁移目标。

### 1.2 已具备能力

| 能力 | 当前状态 | 证据边界 |
|---|---|---|
| jwave 沙箱执行 | 已完成 | 有超时、内存、PID、只读文件系统和网络隔离 |
| LLM 自动纠错 | 已完成 | 最多 7 次；主要由执行错误驱动 |
| 参数校验 | 已完成 | Nyquist、CFL、网格、PML、3D 内存等确定性规则 |
| 结果解析与可视化 | 已完成 | 峰值、RMS、场形状、热力图和波形图 |
| 多轮对话 | 已完成 | 历史测试上下文正确率 95% |
| 物理基准 | 已完成第一版 | VAL-1 覆盖 2D/3D 传播、界面和频域衰减共 5 类场景 |
| 纠错缓存 | 已完成 | 保存错误签名和修复提示，不是成功技能库 |
| 执行看板 | 已完成基础版 | 已有 execution、analysis、LLM usage 数据，但关联性不足 |
| 成功技能预检索 | 未实现 | 当前代码生成前没有检索已验证成功代码 |
| 自动学习质量门 | 未实现 | 当前没有足以支撑自动学习的场景级物理判据 |

### 1.3 当前必须诚实陈述的技术边界

1. 历史 96% 是执行级成功率，不能解释为 96% 物理正确率。
2. VAL-1 证明 jwave 在指定基准设置下能复现解析规律，不代表任意生成场景都自动通过了 VAL-1。
3. 当前 `analysis._verdict()` 主要检查退出状态、NaN/Inf、全零场和统一压力上限。`normal` 只代表基本数值健康，不代表任务语义和场景物理正确。
4. `executions` 与 `analysis_events` 当前没有统一 `run_id`，无法可靠证明某条分析记录属于哪次代码执行。
5. 容器内代码和仓库代码存在过哈希不一致，说明发布状态需要重新收敛并记录版本。
6. `docs/TESTING.md` 仍包含已移除的 `/report`、`/demo` 等入口，测试文档与现有产品界面不一致。
7. 系统 Python 未配置 pytest，当前验证更依赖语法检查和历史脚本，缺少稳定的低成本自动回归层。
8. BYOK 自定义 `base_url` 会触发服务端外连，必须防范 SSRF；浏览器 `localStorage` 保存 API Key 也不应被视为生产级凭据方案。
9. 看板重跑和清空接口属于高影响操作，需要确认鉴权、来源校验和审计链，而不能只依赖页面不可见。

这些边界不是文档瑕疵，而是后续可信学习能否成立的前置条件。

---

## 2. 总体目标、非目标和架构决策

### 2.1 总体目标

到本轮规划结束时，系统应达到以下状态：

- 每次仿真都能从用户需求追溯到参数、生成代码、每次尝试、分析结论、模型成本和最终结果。
- 系统明确标注结果的证据等级，不用一个 `normal` 覆盖所有可信性含义。
- 只有达到场景级物理门控的运行才能成为可自动注入的技能。
- 相似请求在代码生成前能检索到历史成功技能，并给出匹配原因和适用范围。
- 技能库带来的收益通过同题、同环境、可重复的 A/B 测试验证。
- 技能检索或学习出现问题时，可以通过 feature flag 即时回退到现有静态知识库流程。

### 2.2 本轮非目标

- 不迁移到 Open Interpreter。
- 不替换 jwave executor 或削弱其安全限制。
- 不引入 Milvus、独立向量数据库或新增常驻检索服务。
- 不优先拆分多智能体角色。
- 不把 BYOK 扩展到整个代码生成和纠错链路。
- 不宣称达到工业仿真认证或替代 COMSOL、k-Wave 的验证体系。
- 不在证据等级不足时自动学习全部“成功退出”的代码。

### 2.3 已确认架构决策

| 编号 | 决策 | 理由 |
|---|---|---|
| ADR-01 | 保留 Dify 作为当前编排层 | 已有工作流、知识库和多轮链路，迁移收益不足以覆盖风险 |
| ADR-02 | 保留 FastMCP 模块化网关 | 工具边界清晰，适合新增检索工具 |
| ADR-03 | 保留受限 jwave executor | 它是系统安全边界和环境可复现基础 |
| ADR-04 | 成功技能使用独立 `skill_store.py` 和 SQLite | 数据量小、便于审计、部署成本低 |
| ADR-05 | 保留 `error_fix_cache` | 错误修复经验与成功场景技能语义不同，不强行混表 |
| ADR-06 | 自动写库走内部函数，不新增公开写入型 MCP 工具 | 减少提示注入或外部调用污染技能库的风险 |
| ADR-07 | 对外新增只读 MCP 工具 `search_simulation_skill` | 满足 Dify 生成前检索需求，攻击面可控 |
| ADR-08 | 先结构化检索，再考虑语义向量 | 场景标签和物理参数比纯文本相似度更可靠 |
| ADR-09 | 先影子运行，再允许技能影响生成 | 先测召回质量，避免未验证检索直接改变线上结果 |
| ADR-10 | 质量门控由确定性代码负责 | LLM 可解释结果，但不能独自决定技能准入 |

---

## 3. 技术可信性模型

### 3.1 五级证据等级

每次运行和每个技能都必须标注证据等级：

| 等级 | 名称 | 必要条件 | 可以做什么 |
|---|---|---|---|
| Q0 | 已执行 | 有完整运行记录 | 仅用于故障分析 |
| Q1 | 数值有效 | `exit_code=0`、未超时、有限值、非零、未发散 | 可展示，但必须标注“未验证物理正确性” |
| Q2 | 参数可接受 | Q1 + 参数校验通过 + 几何/PML/内存规则通过 | 可成为候选技能 |
| Q3 | 场景物理通过 | Q2 + 对应场景的确定性物理规则通过 | 可成为 active 技能并参与自动注入 |
| Q4 | 参考基准通过 | Q3 + 解析解、已知基准或独立求解器对照 | 高置信技能，可作为回归基准 |

当前 `verdict=normal` 最多映射到 Q1，不能直接映射到 Q3。

### 3.2 场景级物理门控

质量门采用“公共规则 + 场景规则”的组合：

公共规则：

- 执行成功且未超时；
- 输出字段完整；
- 数值为有限值；
- 场不全零；
- 峰值、RMS 和场尺寸在合理范围；
- 参数校验通过；
- 源、传感器和目标区域不落入 PML；
- 3D 内存预算符合 executor 约束。

场景规则第一批覆盖：

| 场景 | 规则示例 |
|---|---|
| 2D 均匀点源 | 远场包络随距离近似 `1/sqrt(r)`，容差由网格和近场距离决定 |
| 3D 均匀点源 | 包络随距离近似 `1/r`；探针必须在物理区内 |
| 平面波无损传播 | 指定位置振幅比接近 1，且横向孔径满足基准要求 |
| 平界面 | 反射/透射系数与阻抗公式在容差内 |
| 频域衰减 | 几何扩散乘指数衰减，与 `Im(k)` 预测一致 |
| 初始压力场 | 初始峰值、传播后非零性和能量变化在经验/解析范围内 |
| 未知复杂异质场景 | 只能达到 Q2，除非提供可验证的守恒、对称性或对照指标 |

规则必须返回结构化证据：`check_id`、测量值、期望值、容差、通过状态和说明。

### 3.3 可信声明规则

用户报告和看板必须按证据等级表述：

- Q1：结果数值有效，但未完成场景物理验证。
- Q2：参数和数值条件满足已知约束，复杂物理结论仍需人工判断。
- Q3：通过当前场景的确定性物理规则。
- Q4：与解析解或独立参考基准在给定容差内一致。

不得使用“VAL-1 已通过”推导所有后续仿真均可信。

---

## 4. 目标架构

```text
用户请求
  -> Dify 需求理解与参数提取
  -> validate_simulation_params
  -> search_simulation_skill                 [新增，只读]
  -> 代码生成（静态知识 + top-k 技能 + 适用范围）
  -> run_jwave_code_with_retry
       -> jwave executor                      [安全边界保持不变]
       -> error_fix_cache                     [失败后纠错经验]
  -> analyze_simulation_result
  -> physics_gate                             [新增，确定性质量门]
  -> 结果解释与证据等级展示
  -> skill_store.record_candidate_internal    [新增，内部写入]
  -> 技能生命周期与审计
```

### 4.1 模块职责

| 模块 | 主要职责 |
|---|---|
| `skill_store.py` | SQLite schema、迁移、去重、版本、查询、状态和事件 |
| `skill_retrieval.py` | 结构化过滤、评分、top-k 和匹配理由；数据量小时可并入 `skill_store.py` |
| `physics_gate.py` | 证据等级计算、公共规则和场景级确定性检查 |
| `tools.py` | 注册 `search_simulation_skill`，保持仿真工具职责 |
| `execution.py` | 执行、代码清理、字段收缩和报告；不承担物理判定 |
| `analysis.py` | 数据提取、基础指标和图像生成；输出 Q1 所需证据 |
| `dashboard.py` | 运行、分析、成本、技能统计的读模型 |
| `portal.py` | Web 路由和经过鉴权的管理操作 |
| Dify 工作流 | 参数提取、检索调用、代码生成、解释和有限重试 |

### 4.2 统一运行信封

每次仿真创建不可变 `run_id`，建议使用 UUID。核心数据结构：

```json
{
  "run_id": "...",
  "request_text": "...",
  "session_id": "...",
  "scenario_type": "point_source_2d",
  "normalized_params": {},
  "initial_code_hash": "...",
  "final_code_hash": "...",
  "attempt_count": 2,
  "execution_status": "succeeded",
  "analysis_verdict": "normal",
  "quality_level": "Q3",
  "physics_checks": [],
  "skill_ids_retrieved": [],
  "skill_ids_injected": [],
  "model_usage": {},
  "software_version": {
    "git_commit": "...",
    "jwave": "0.2.1",
    "validator_version": "..."
  }
}
```

`run_id` 必须写入执行记录、分析记录、技能事件和 A/B 记录。任何缺少关联证据的历史记录都不能自动转为 active 技能。

---

## 5. 成功技能库设计

### 5.1 数据库边界

第一阶段使用 `/app/data/skill_store.db`。建议至少包含以下表：

```text
simulation_skills
skill_versions
skill_events
skill_retrievals
```

`simulation_skills` 保存稳定身份和统计；`skill_versions` 保存具体代码、参数范围和验证证据；`skill_events` 保存状态变化；`skill_retrievals` 保存查询、候选、得分和后续结果。

### 5.2 核心字段

| 字段 | 说明 |
|---|---|
| `skill_id` | 稳定 ID |
| `scenario_type` | 受控场景枚举 |
| `state_text` | 人类可读的适用场景 |
| `normalized_params` | 规范化参数 JSON |
| `preconditions` | 参数范围、维度、求解模式和环境要求 |
| `code_template` | 已清洗、可复用代码 |
| `code_hash` | 代码去重和审计 |
| `postconditions` | 预期输出及物理条件 |
| `quality_level` | Q0-Q4 |
| `physics_evidence` | 结构化检查结果 |
| `source_run_id` | 来源运行 |
| `validator_version` | 质量门版本 |
| `status` | `candidate/active/questioned/retired` |
| `success_count` / `failure_count` | 复用统计 |
| `created_at` / `updated_at` | 生命周期时间 |

技能库不保存 API Key、Token、完整环境变量、浏览器凭据或未经清洗的 stderr/stdout。

### 5.3 准入规则

```text
候选技能：quality_level >= Q2
自动激活：quality_level >= Q3 且来源证据完整
高置信技能：quality_level == Q4
```

自动入库还必须满足：

- 使用最终成功代码；
- 代码长度不超过现有 20KB 限制；
- 不包含 Markdown、`<think>`、凭据或本机路径；
- 参数可规范化；
- `run_id` 能关联执行和分析；
- 场景类型属于受控枚举；
- 指纹去重成功。

无法达到 Q3 的结果只保存为 candidate，用于观察和人工审核，不参与自动 Prompt 注入。

### 5.4 检索策略

第一阶段使用结构化优先检索：

1. `scenario_type`；
2. 维度与 solver mode；
3. source type；
4. 介质类型和层数；
5. 频率带、网格和空间分辨率范围；
6. 传感器、异质结构、衰减等特征；
7. 文本 token overlap 作为补充。

建议评分：

```text
score = 0.30 * scenario_match
      + 0.20 * solver_dimension_match
      + 0.20 * parameter_feasibility
      + 0.10 * text_similarity
      + 0.10 * wilson_success_lower_bound
      + 0.10 * physical_quality
      - recent_failure_penalty
```

使用 Wilson 下限代替裸成功率，避免“只成功过 1 次”的技能获得 100% 高分。

### 5.5 向量检索升级条件

只有满足以下任一条件才评估向量检索：

- active 技能超过 500 条；
- 标注集 top-3 recall 连续两轮低于 80%；
- 新表达方式导致结构化标签无法覆盖；
- SQLite 检索 P95 超过 200ms 且索引优化无效。

升级时优先复用已有 Dify 向量能力或轻量本地 embedding，不直接引入独立 Milvus 集群。

### 5.6 生命周期

```text
candidate -> active -> questioned -> retired
                 ^          |
                 +----------+
```

- `candidate -> active`：Q3+ 且证据完整；
- `active -> questioned`：最近 3 次使用中失败 2 次，或发生 1 次物理错误；
- `questioned -> active`：重新通过相同或更高版本质量门；
- `questioned -> retired`：连续失败或人工确认不适用；
- 所有变化写入 `skill_events`，不可静默删除历史。

---

## 6. MCP 与 Dify 集成契约

### 6.1 新增 MCP 工具

```text
search_simulation_skill(
  query: str,
  params_json: str = "{}",
  scenario_type: str = "",
  limit: int = 3
)
```

返回结构：

```json
{
  "matched": true,
  "query_id": "...",
  "items": [
    {
      "skill_id": "...",
      "version": 1,
      "score": 0.91,
      "quality_level": "Q3",
      "state": "2D 均匀介质点源",
      "preconditions": {},
      "code_template": "...",
      "postconditions": {},
      "match_reasons": [],
      "success_lower_bound": 0.82
    }
  ]
}
```

安全要求：

- 只返回 `active` 技能；
- `limit` 最大 3；
- 总代码和说明 token 预算受限；
- 不返回凭据或原始日志；
- 每次检索记录 query、候选、得分和耗时。

### 6.2 Dify 节点位置

```text
参数提取
  -> 参数规范化
  -> validate_simulation_params
  -> search_simulation_skill
  -> 代码生成
```

代码生成 Prompt 必须明确：

- 技能是已验证参考，不是不可修改的最终答案；
- 只能在 `preconditions` 范围内复用；
- 当前参数与技能不同之处必须显式调整；
- 静态 jwave API 规则和黑名单仍然有效；
- 无可靠命中时回退现有知识库。

### 6.3 自动学习调用位置

自动学习不作为公开 MCP 工具。流程为：

```text
执行完成
  -> analysis 输出基础指标
  -> physics_gate 计算 Q0-Q4
  -> Q2 保存 candidate
  -> Q3/Q4 允许 active
  -> skill_store 内部写入并记录事件
```

这避免用户或 Prompt 直接调用“写技能”污染长期记忆。

---

## 7. 分阶段实施计划

阶段按门禁推进，不以日期自动切换。未通过前一阶段，不允许开启后一阶段的自动决策能力。

### Phase 0：基线收敛与安全封口（P0，2-4 天）

目标：确认正在开发、测试和部署的是同一版本，并建立可信数据链的前置条件。

| 任务 | 交付物 | 验证 |
|---|---|---|
| OPT-001 发布状态收敛 | 构建并部署当前 `main`；记录 Git SHA、镜像 digest、工作流版本 | 仓库与容器关键文件哈希一致；页面和工具 smoke test 通过 |
| OPT-002 文档基线收敛 | 更新 `TESTING.md`、README 和架构入口，移除已删除路由 | 文档列出的全部 URL 和命令可执行 |
| OPT-003 统一 `run_id` | additive migration；execution/analysis/cost/retrieval 均关联运行 | 20 次 smoke run 关联率 100% |
| OPT-004 可信等级骨架 | 新增 Q0-Q4、公共 gate 和结构化证据 | 当前 `normal` 只能生成 Q1；单测覆盖异常值、全零、PML 等 |
| OPT-005 BYOK 与管理接口安全审计 | SSRF 防护、敏感字段脱敏、重跑/清空接口鉴权与审计 | 私网/环回/非法 scheme 请求被拒；未授权操作失败 |
| OPT-006 测试运行时 | 增加开发测试依赖和低成本 test target | 单元测试可在 VM 或独立测试容器重复运行 |

Phase 0 门禁：

- [ ] 部署版本可追溯到 Git SHA；
- [ ] 仓库、容器、Dify 工作流和测试文档一致；
- [ ] 新运行 `run_id` 关联率 100%；
- [ ] 管理接口和 BYOK 安全测试通过；
- [ ] VAL-1 全部通过；
- [ ] 原有标准场景没有回归。

### Phase 1：可信技能库 MVP（P0，4-7 天）

目标：建立只接收有证据运行的 SQLite 技能资产。

| 任务 | 文件/产出 | 验证 |
|---|---|---|
| SKL-001 数据模型与迁移 | 新增 `skill_store.py` | 新库创建、重复迁移、并发读写和备份恢复通过 |
| SKL-002 参数规范化 | 场景枚举、单位归一、规范 JSON | 等价参数产生相同场景指纹 |
| SKL-003 场景物理门 | 新增 `physics_gate.py` | VAL-1 场景产生 Q4；伪造全零/超 PML/错误衰减被拒绝 |
| SKL-004 去重与版本 | 指纹、版本、状态事件 | 同场景重复成功更新统计，不无限复制 |
| SKL-005 只读检索工具 | `search_simulation_skill` | MCP schema 正确；只返回 active；top-k 和 token 预算生效 |
| SKL-006 种子技能 | 从 VAL-1 和稳定模板生成 8-12 个 Q3/Q4 技能 | 每个技能有 source run、validator version 和物理证据 |

Phase 1 门禁：

- [ ] 所有 active 技能达到 Q3 或 Q4；
- [ ] Q1/Q2 无法自动激活；
- [ ] 凭据和绝对路径扫描为零；
- [ ] 去重、版本、质疑、退役事件可审计；
- [ ] 检索 P95 小于 200ms；
- [ ] executor 安全配置未改变。

### Phase 2：影子检索与召回评估（P1，3-5 天）

目标：让检索在线运行但暂不影响代码生成，先证明召回质量。

| 任务 | 产出 | 验证 |
|---|---|---|
| RET-001 Dify 影子节点 | 参数提取后调用 search，不注入生成 Prompt | 原流程输出不变，检索日志完整 |
| RET-002 标注查询集 | 至少 30 个已知、近似和未知场景 | 每题有期望技能或“应无匹配”标签 |
| RET-003 排序校准 | 结构化权重、Wilson 下限、失败惩罚 | top-3 recall ≥85%，错误高置信命中 ≤5% |
| RET-004 无匹配策略 | 最低分阈值和清晰 fallback | 未知场景不强行返回技能 |
| RET-005 可观测性 | 命中率、延迟、候选分布、无匹配率 | 看板/离线报告可复核 |

Phase 2 门禁：

- [ ] 标注集 top-1 accuracy ≥70%；
- [ ] top-3 recall ≥85%；
- [ ] 不应匹配场景的高置信误召回 ≤5%；
- [ ] P95 检索延迟 <200ms；
- [ ] 影子检索不改变现有最终成功率和成本。

### Phase 3：受控技能注入与 A/B 验证（P1，5-8 天）

目标：证明技能库提高真实物理成功率，再逐步全量。

| 任务 | 产出 | 验证 |
|---|---|---|
| INJ-001 Feature flags | `SEARCH_SKILL_ENABLED`、`SKILL_INJECT_ENABLED`、`SKILL_LEARN_ENABLED` | 任一功能可独立关闭并立即回退 |
| INJ-002 Prompt 注入 | 只注入 top 1-3 active 技能及适用范围 | Prompt token 增量受控，当前参数差异被显式处理 |
| INJ-003 配对 A/B | 同一请求集比较静态知识库与技能注入 | 使用相同环境和模型配置，记录运行证据 |
| INJ-004 学习闭环 | 使用结果更新技能统计和状态 | 物理错误立即触发 questioned，不被继续优先注入 |
| INJ-005 回归与故障演练 | VAL-1、50 次回归、多轮、错误注入 | 回退开关、数据库故障和空库路径均可用 |

A/B 主要判据：

- 首次 Q3+ 成功率相对基线提升至少 10 个百分点，或平均重试次数下降至少 20%；
- 最终 Q3+ 成功率不得下降超过 2 个百分点；
- 平均模型成本不增加超过 10%，除非首次物理成功率提升具有明确收益；
- 不得增加高置信物理错误；
- 使用 Wilson 区间展示结果，不只报告单个百分比。

Phase 3 门禁：

- [ ] A/B 达到主要判据；
- [ ] VAL-1 全通过；
- [ ] 技能库不可用时自动回退；
- [ ] 没有未关联 `run_id` 的自动学习记录；
- [ ] 自动退役策略经过故障注入验证。

### Phase 4：产品化、用户验证与 v1.0（P2，1-2 周）

目标：把可信性和技能能力变成用户可理解、开发者可维护的产品能力。

| 任务 | 产出 | 验证 |
|---|---|---|
| PRD-001 技能审计页 | `/skills`、状态、证据、来源、使用记录 | 用户能查看技能为何可信、为何退役 |
| PRD-002 报告可信标签 | Q 等级、通过规则、未验证边界 | 不再用模糊“正常”替代证据说明 |
| PRD-003 统一 benchmark | 一键生成执行、物理、检索、成本报告 | 同一版本可重复运行并比较趋势 |
| PRD-004 5 人 UAT | 研究者/学生完成指定任务 | 阻塞问题为 0，满意度 ≥4/5 |
| PRD-005 开源与部署文档 | README、DEPLOY、CONTRIBUTING、LICENSE | 新开发者 30 分钟内完成首次可信仿真 |
| PRD-006 发布 | `v1.0.0` 标签和发布说明 | 门禁全部完成，部署可回滚 |

---

## 8. 原规划任务迁移

| 原任务 | 新状态 |
|---|---|
| 阶段一 T-001 至 T-006 | 已完成，作为历史执行稳定性基线 |
| 阶段二 VAL-1、T-007 至 T-012 | 已完成，作为当前闭环和物理基准起点 |
| 原 T-013 知识库扩展 | 文档已创建；Dify 索引状态在 OPT-002 复核 |
| 原 T-014 Dashboard 增强 | 部分完成；部署一致性和接口安全并入 OPT-001/005 |
| 原 T-015 仿真方案推荐 | 被技能检索和结构化参数推荐吸收，不单独做 Prompt 功能 |
| 原 T-016 5 人验收 | 移至 Phase 4 PRD-004 |
| 原 T-017 文档和开源 | 移至 Phase 4 PRD-005/006 |
| BYOK P0 | 作为实验功能保留，先完成 OPT-005 安全封口 |
| BYOK P1-P3 | 暂缓，待技能库和统一 benchmark 稳定后重新评估 |

---

## 9. 测试与评测体系

### 9.1 测试层级

| 层级 | 内容 | 是否调用模型 |
|---|---|---|
| L1 单元测试 | store、gate、rank、参数规范化、迁移 | 否 |
| L2 契约测试 | MCP schema、返回结构、feature flag、错误码 | 否 |
| L3 集成测试 | 网关 + SQLite + executor + 分析链路 | 通常否 |
| L4 物理回归 | VAL-1 和新增场景规则 | 否 |
| L5 工作流 E2E | Dify 参数提取、生成、执行、解释 | 是 |
| L6 配对 A/B | 有无技能注入的同题比较 | 是 |
| L7 安全测试 | SSRF、鉴权、凭据、恶意代码、资源上限 | 否/少量 |

### 9.2 统一指标

必须同时报告：

- execution success rate；
- Q1、Q2、Q3、Q4 分布；
- first-attempt Q3+ success rate；
- final Q3+ success rate；
- 平均和 P95 重试次数；
- 平均和 P95 端到端耗时；
- token 与估算成本；
- 技能 top-1/top-3 命中率；
- 技能注入采纳率；
- 错误高置信召回率；
- questioned/retired 技能数量；
- 未关联 run 记录数量。

### 9.3 基准集扩展

在 VAL-1 基础上逐步增加：

- 网格收敛性测试；
- PML 厚度敏感性；
- 源/传感器位置边界；
- 异质介质对称性和阻抗趋势；
- 初始压力的能量与非零性；
- 3D 内存和运行时预算；
- 未知 API 和错误注入；
- 技能误召回和错误技能退役。

扩展基准必须记录公式、单位、容差来源、软件版本和可重复命令。

---

## 10. 安全、隐私与运行边界

### 10.1 executor 红线

以下设置不可因技能库或自省功能而削弱：

- `read_only` 根文件系统；
- `cap_drop: ALL`；
- `no-new-privileges`；
- PID、CPU、内存和超时限制；
- executor 无外网；
- 代码长度限制；
- 共享 Token 鉴权。

技能代码始终通过 executor 执行，不允许在 MCP 网关进程中 `exec()`。

### 10.2 BYOK 安全

在继续扩展 BYOK 前必须：

- 只允许 `https`；开发环境例外必须显式配置；
- DNS 解析后阻止 loopback、link-local、私网、metadata IP 和重绑定；
- 禁止自动跟随跨域重定向；
- 限制端口、请求体、响应体和超时；
- API Key 不写日志、数据库、异常详情或技能库；
- 页面明确说明 Key 会随请求发送到本服务；
- 评估使用 session memory 替代长期 `localStorage`。

### 10.3 管理接口

重跑、清空、技能退役、手工激活和批量导入必须具备：

- 身份认证；
- 权限校验；
- CSRF/Origin 防护；
- 审计事件；
- 明确目标 ID；
- 可恢复或可追溯结果。

---

## 11. 可观测性与运行目标

### 11.1 关键事件

```text
run_created
params_validated
skill_retrieved
skill_injected
execution_attempted
analysis_completed
physics_gate_completed
skill_candidate_created
skill_activated
skill_questioned
skill_retired
run_completed
```

每个事件包含 `run_id`、时间、版本和必要的非敏感上下文。

### 11.2 性能预算

| 项目 | 目标 |
|---|---:|
| 技能检索 P95 | <200ms |
| 质量门计算 P95 | <100ms，不含仿真本身 |
| 技能写入 P95 | <500ms |
| 注入额外 Prompt | <3000 tokens，优先 <1500 |
| 标准 2D 端到端 P95 | <60s |
| 数据库故障回退 | 不阻塞基础仿真 |

### 11.3 数据保留

- 技能事件永久保留或按版本归档；
- 大型 base64 图像不进入技能库；
- 执行 stdout/stderr 按大小和期限清理；
- 所有清理策略先备份并记录审计；
- 数据库 schema 采用 additive migration，禁止无备份破坏性变更。

---

## 12. 发布、回滚和配置

建议新增配置：

```text
SKILL_STORE_PATH=/app/data/skill_store.db
SEARCH_SKILL_ENABLED=false
SKILL_INJECT_ENABLED=false
SKILL_LEARN_ENABLED=false
SKILL_MIN_SCORE=0.70
SKILL_MAX_RESULTS=3
PHYSICS_GATE_VERSION=v1
```

发布顺序：

1. 数据库迁移和观测字段；
2. 质量门，只记录不改变结果；
3. 技能写入 candidate；
4. 只读检索影子运行；
5. 小流量 Prompt 注入；
6. A/B 达标后扩大；
7. 最后开启自动状态降级和学习。

回滚要求：

- 关闭三个 feature flags 即回到现有静态知识库链路；
- 新表不覆盖 `error_fix_cache` 和 execution history；
- 每次迁移前备份 SQLite；
- Dify 工作流修改前保存 graph；
- 失败发布不删除 candidate/事件，只停止使用。

---

## 13. 工作顺序和协作纪律

### 13.1 当前执行顺序

```text
OPT-001/002/005
  -> OPT-003/004/006
  -> SKL-001/002
  -> SKL-003/004
  -> SKL-005/006
  -> RET-001~005
  -> INJ-001~005
  -> PRD-001~006
```

### 13.2 提交原则

- 每个任务一个可回滚提交；
- 修改 Dify 工作流必须提交 graph 备份；
- 功能提交必须包含相应测试或验证记录；
- 规划和状态变化同步到 `CHANGELOG.md`；
- 临时迁移、调试和一次性生成脚本使用后删除；
- 只有可重复使用脚本进入 `scripts/`；
- 不提交 `.env`、日志、缓存、tar 包、测试临时产物或本机绝对路径。

### 13.3 变更完成定义

任务只有同时满足以下条件才算完成：

- 代码或文档产出已提交；
- 自动检查通过；
- 对应门禁有可复核证据；
- 未削弱安全边界；
- 失败和回滚路径已验证；
- CHANGELOG 已记录；
- Git 工作区干净。

---

## 14. 近期两周建议排期

### 第一周：可信基线

1. 部署并核验当前 `main`；
2. 修正文档和现有路由测试；
3. 审计 BYOK、重跑和清空接口；
4. 添加 `run_id` 和版本字段；
5. 建立 Q0-Q4 骨架与单元测试；
6. 重跑 VAL-1 和低成本 smoke set。

### 第二周：技能库 MVP

1. 实现 `skill_store.py`；
2. 完成参数规范化和 schema migration；
3. 实现首批场景 gate；
4. 从 VAL-1 和稳定模板生成种子技能；
5. 注册 `search_simulation_skill`；
6. 建立 30 题检索标注集并完成离线评估。

两周结束时，检索仍以影子模式为主。只有 Phase 1、Phase 2 门禁通过后，才允许技能进入代码生成 Prompt。

---

## 15. 最终验收标准

本规划完成的最低标准：

- [ ] 部署、代码、工作流和文档版本一致；
- [ ] 100% 新运行具有完整 `run_id` 证据链；
- [ ] 报告明确区分 Q0-Q4；
- [ ] 至少 8 个 Q3/Q4 active 技能；
- [ ] `search_simulation_skill` 可用且 top-3 recall ≥85%；
- [ ] 自动学习不会接收 Q0-Q2 为 active；
- [ ] 技能注入 A/B 达到收益门槛且无物理正确率退化；
- [ ] VAL-1 持续全部通过；
- [ ] executor 安全限制不变；
- [ ] 技能库故障可自动回退；
- [ ] 5 人 UAT 满意度 ≥4/5；
- [ ] 新开发者 30 分钟内完成首次带证据等级的仿真；
- [ ] 发布 `v1.0.0`。

---

## 16. 参考资料

- 袁雪峰，丁俐夫，陈颖，等：《基于大语言模型的电力仿真智能体及其技能库设计方法》，《电力系统自动化》，2026，50(13)：177-188。
- CloudPSS-SimAgent 开源实现及其成功技能、调试技能数据。
- AcouAgent `docs/VALIDATION_BASELINE.md`。
- AcouAgent `docs/TESTING.md`。
- AcouAgent `docs/ARCHITECTURE.md`。
- AcouAgent `docs/PRD.md`。
- 《智能体仿真项目优化方向》v1.5。

---

## 17. 版本记录

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-08-08 | 原三阶段开发规划 |
| v2.0 | 2026-09-27 | 以技术可信性和成功技能库为主线重写，替代原阶段三及后续规划 |
