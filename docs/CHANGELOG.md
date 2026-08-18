# 变更日志

> 记录每次开发会话的变更，按时间倒序。

---

## 2026-08-18 · 会话: T-008 工作流改造完成并发布（审查+解释节点上线）

### 完成
- [x] **T-008 结果审查 + 解释节点**（Dify 工作流 9 → 13 节点，改造脚本 `_build_graph.py` 可复现）：
  - 代码生成 prompt 注入**场数据输出模板**（LLM 生成的代码自动输出 `__ACOU_FIELD_START__/END__` 压力场 JSON）
  - 新增节点链：MCP retry → **解包代码节点**（拆 stdout/stderr/exit_code）→ **analyze_simulation_result 工具节点** → **结果审查 LLM 节点**（pass/retry/fail）→ **结果解释 LLM 节点**（≥3 句物理解读）→ 代码执行（合并 report+审查+解读）→ end
- [x] **发布新版工作流**：解决历史遗留——线上 published 一直跑旧版（app.workflow_id 指向 3d05c047，8 节点旧版）；本次将新 graph 写入 app 实际引用的行 + draft + published 三处一致
- [x] 更新 **tool_mcp_providers.tools 缓存**：新增 analyze_simulation_result 工具定义（否则 Dify 报 Tool not found）

### 验证（VM 真实端到端）
- `/v1/workflows/run` 真实仿真（200kHz 水中传播，96×96）→ status=succeeded，输出含：
  仿真结果报告 ✓ 场数据标记 ✓ **物理解读 ✓**（含数值/物理直觉/几何衰减判断，verdict 正确判 normal）
- 审查 verdict=pass 时不输出警告（符合设计）；`<think>` 推理块已剥离

### 踩坑记录（供后续）
1. **Dify 发布机制**：运行用的是 `apps.workflow_id` 指向的版本行（version=时间戳），不是 version='published' 的行——改工作流必须写 app 指向的行
2. **Dify MCP 工具节点只暴露 `json` 输出变量**（整个返回），取子字段需插入代码节点拆包
3. **代码节点 outputs 声明必须覆盖返回键**（返回 3 键但声明只有 result → 节点失败）
4. **exit_code 不能用 `or 1`**（0 是 falsy，会把成功变失败）→ 用 None 检查
5. **MCP 工具新增后要同步 tool_mcp_providers.tools 缓存**（DB 字段，工具定义实时从网关拉但缓存校验）

### 遗留（T-009 处理）
- 审查 retry/fail 尚未接回参数提取（迭代循环 ≤3 次，属 T-009）
- 校验节点（validate_simulation_params）从未进入任何工作流版本（README 描述与实际不符，建议 T-009 补）
- 审查节点输出建议收紧为严格 JSON（当前 pass/retry/fail 文本）

### 变更文件
- `_build_graph.py` — 工作流改造构造脚本（可复现，保留进仓库）
- `docs/dify_workflow_backup/` — 改造前后 graph 备份（draft/published/live）
- 文档：`docs/AGENTS.md`、`docs/DEVELOPMENT_PLAN.md`、`docs/ARCHITECTURE.md`

### 当前状态
- 阶段二：VAL-1 ✅、T-007 ✅、**T-008 ✅（已发布上线）**
- 下个任务: T-009（迭代循环：审查 retry 回参数提取 ≤3 次）

---

## 2026-08-18 · 会话: T-007 analyze_simulation_result 完成（含 VM 端到端验证）

### 完成
- [x] **T-007 结果分析工具**：`analysis.py` 实现 `analyze_simulation_result`（模块化落点）
  - 解析 stdout 场数据 JSON（`__ACOU_FIELD_START__/__ACOU_FIELD_END__` 标记）
  - 物理量摘要：max_pressure / rms_pressure / field_shape / has_signal
  - 热力图 + 波形图 PNG → base64（matplotlib 3.9.4，Agg 无头模式）
  - verdict 判定（对标 VAL-1 基准）：`normal` / `zero_field` / `abnormal`
    （abnormal=执行失败/无场数据/NaN/Inf/数值发散>1e12 Pa；zero_field=全零场）
  - 降级路径：无 matplotlib → ASCII 热力图；无 numpy → 纯 Python 计算
  - `FIELD_OUTPUT_SNIPPET` 常量：可注入仿真代码的场输出模板（T-008 接入工作流时复制即用）
- [x] 网关依赖：`requirements.lock.txt` 增加 `numpy==2.1.3` + `matplotlib==3.9.4`（python 3.11 兼容）
- [x] 修复 MPLCONFIGDIR：容器只读 HOME 下 matplotlib 强制使用 /tmp 缓存

### 验证（VM 实测）
- 单元分支：normal / zero_field / no-field / exit-1 / NaN / Inf / 发散 / 1D 波形 全部符合预期
- 真实仿真端到端（MCP 协议）：run_jwave_code 跑 64×64 点源仿真 → analyze_simulation_result
  返回 verdict=normal、max=0.35094（与仿真一致）、热力图 PNG 25KB（magic 校验通过）、波形图 17.8KB
- MCP tools/list → 7 个工具（新增 analyze_simulation_result）
- /health 200；容器日志无错误

### 重要发现（遗留问题）
- ⚠️ **线上 published 工作流仍是 08-07 的 8 节点旧版**（`e0a92c7a`，updated 08-07 15:08）；
  校验节点 + 代码执行节点只存在于 draft（`641c4530`，9 节点）**从未发布**。
  因此线上 `/v1/workflows/run` 跑的是旧链路——T-008 改造工作流时必须一并**发布新版**
  （含代码节点、校验节点、analyze 节点），否则新功能不生效。
- 顺带排掉一个 jwave 坑：`tone_burst()` 实际返回 152 采样（非标称 150），
  Nt < 152 时 `zeros(Nt-len)` 会得到负维度导致 `broadcast_in_dim got (-2,)`；
  信号补齐需先裁剪 `sig[:Nt]`。建议后续补进纠错速查表。

### 变更文件
- `analysis.py` — analyze_simulation_result 工具 + FIELD_OUTPUT_SNIPPET + 降级路径
- `requirements.lock.txt` — +numpy/matplotlib
- 文档：`docs/AGENTS.md`（任务状态）、`docs/DEVELOPMENT_PLAN.md`（门禁/进度）、`docs/ARCHITECTURE.md`（3.1 标注）

### 当前状态
- 阶段二：VAL-1 ✅、**T-007 ✅（工具层面）**；工作流联动属 T-008
- 下个任务: T-008（工作流审查+解释节点，需同时发布新版工作流）

---

## 2026-08-18 · 会话: 网关模块化重构（server_safe.py 1074 行 → 薄壳 + 7 模块）

### 动机
- `server_safe.py` 1074 行混含四类职责（MCP 工具 / Web 门户 / 纠错缓存 / 报告生成），且 T-007/P2 等新功能还要继续往里加，属"上帝文件"苗头。

### 完成
- [x] 拆分为职责清晰的模块（`register(mcp)` 模式，避免循环导入）：
  - `config.py` — 环境配置与校验（30 行）
  - `cache_store.py` — 纠错经验缓存 SQLite + 统计（原 L122-366）
  - `execution.py` — 代码清理/沙箱执行/Markdown 报告（原 `_clean_code`/`_execute_code`/`_build_report`）
  - `llm.py` — DeepSeek 自动纠错（原 `_llm_fix_code`）
  - `tools.py` — 6 个 MCP 工具（原 L624-1069，`register(mcp)` 注册）
  - `portal.py` — 12 条 Web 路由（原 L473-621，`register(mcp)` 注册）
  - `analysis.py` — 结果分析占位（**T-007 analyze_simulation_result 落点**）
  - `server_safe.py` — 薄壳入口（约 60 行）：装配 + 注册 + main，Dockerfile APP_FILE 不变
- [x] Dockerfile COPY 行纳入全部新模块
- [x] 清理：`server_safe.py` 中原死代码 `import base64` 已移除

### 验证（VM 实测，全部通过）
- 本机 + VM 双端 `py_compile` 通过
- 镜像重建 + 容器重启成功；日志无 error/traceback
- `/health` 200；门户 6 路由（/ /portal /dashboard /report /cache /demo）全部 200
- MCP `tools/list` → 6 个工具齐全；`jwave_environment` 真实调用 OK
- `run_jwave_code` 端到端执行 OK（exit 0，63ms）；看板 executions API 记录已持久化

### 变更文件
- 新建：`config.py` `cache_store.py` `execution.py` `llm.py` `tools.py` `portal.py` `analysis.py`
- 重写：`server_safe.py`（薄壳化）、`Dockerfile`（COPY 行）
- 文档：`docs/ARCHITECTURE.md`（3.1 节）、`README.md`（工具/语法预检行）、`docs/AGENTS.md`（文件清单 + 模块化约定）

### 当前状态
- 阶段二 VAL-1 ✅；网关已模块化，T-007 落点 `analysis.py` 就绪
- 下个任务: T-007（analyze_simulation_result）

---

## 2026-08-18 · 会话: 阶段二 VAL-1 验证基准集完成（3/3 PASS）

### 完成
- [x] **VAL-1 验证基准集**：新建 `executor/validation_baseline.py` + `docs/VALIDATION_BASELINE.md`
- [x] 三用例全部误差 < 1%（门禁通过，4/4 项，3 项 < 0.01%）：
  - 用例1 平面波振幅守恒：比值 1.0000016（误差 **0.0002%**）
  - 用例2 圆柱波远场 1/√r 衰减：0.74990 vs 理论 0.75593（误差 **0.80%**）
  - 用例3 平界面反射/透射：R=0.538479（**0.003%**）、T_p=1.538432（**0.002%**）
- [x] 在 executor 容器内实测通过（VM `~/dify-mcp-server/executor/validation_baseline.py` 已同步，可一键重跑，零模型费用）

### 关键实测发现（已写入 VALIDATION_BASELINE.md，供 T-007 直接复用）
- jwave 2D 求解器对应圆柱波 **1/√r** 衰减（规划文档"1/r"为 3D 球面波，需修正）
- PML y 向软孔径横向泄漏：Ny=64 时振幅衰减 0.5→0.34，Ny≥256 时守恒到 0.1% 内
- jwave 自带 `analytic_signal` 有缺陷（清零正频率+去 DC），且 Hilbert 包络有 1/t 尾部；
  峰值测量改用 **cfl=0.1 细采样 + 窄时间窗 + 原始信号最大值**（4 组对比度扫描验证 R/T <0.2%）
- `Sources` 的 signals 必须补齐到 Nt 长度；`Sensors` 位置约定有歧义，改用全场索引 `p[n,x,y,0]`

### 变更文件
- `executor/validation_baseline.py` — 新建（基准脚本，3 用例可一键重跑）
- `docs/VALIDATION_BASELINE.md` — 新建（场景/理论/实测/误差/收敛性/复用指引）
- `docs/DEVELOPMENT_PLAN.md`、`docs/AGENTS.md` — VAL-1 状态更新

### 当前状态
- 阶段一 ✅ 已关闭；**阶段二 VAL-1 ✅ 完成（P0 地基就绪）**
- 下个任务: 阶段二 T-007（analyze_simulation_result，matplotlib 3.11.1 已就绪）

---

## 2026-08-17 · 会话: 阶段一收尾 + 开发规划校准（文档类低风险变更）

### 完成
- [x] 核对开发规划（`docs/DEVELOPMENT_PLAN.md`）：阶段一 T-001~T-006 全部完成，T-006 实测 96%（48/50）已过门禁
- [x] 补打 `git tag phase-1-complete`（阶段一正式关闭，此前未打）
- [x] 修复 `docs/AGENTS.md` 与 `docs/DEVELOPMENT_PLAN.md` 任务编号冲突：新增编号映射表（AGENTS.md T-001~T-010 ↔ PLAN.md T-001~T-017），T-001/T-002/T-003 标记 [DONE]
- [x] 更新 `docs/DEVELOPMENT_PLAN.md`：3.3 门禁清单勾选、附录进度表 T-006 → ✅ 96%、标注 P2「2D均质初始压力 80%」遗留
- [x] 提交仓库：`docs/` 三份文档 + HANDOFF，push 到 origin/main，tag 一并推送

### 变更文件
- `docs/DEVELOPMENT_PLAN.md` — 门禁勾选 + 进度表更新 + 阶段一关闭说明
- `docs/AGENTS.md` — 编号映射表 + [DONE] 标记
- `docs/CHANGELOG.md` — 本记录
- `docs/HANDOFF_2026-08-17.md` — P1 修复标记（此前会话）

### 当前状态
- 阶段一 ✅ 正式关闭（tag phase-1-complete）
- 阶段二未开始；P2（2D均质初始压力 80%）为阶段一遗留质量项
- 下个任务: 阶段二 T-007（analyze_simulation_result，需先确认 executor 有 matplotlib）或 P2

---

## 2026-08-17 · 会话: P1 修复 .env 中 MCP_AUTH_TOKEN 重复两行

### 完成
- [x] P1: 实测确认 VM `~/dify-mcp-server/.env` 中 `MCP_AUTH_TOKEN=` 重复 2 行（第 1、3 行，值相同 64 位 hex，sha256 `29920d60…`）
- [x] 顺带发现并确认 `MCP_EXTRA_MODULES=` 也重复 2 行（第 2、4 行，值相同 7 字符）——HANDOFF 未记录
- [x] 备份 `.env` → `.env.bak.20260817_125722`，用 `awk -F= '!seen[$1]++'` 按键去重保留首次出现，8 行 → 6 行
- [x] `docker compose up -d --force-recreate dify-mcp` 重建容器，容器内 `MCP_AUTH_TOKEN` len=64 且与 .env 文件一致

### 验证
- `/health` → 200 "ok"
- MCP `initialize`（Bearer + Accept: application/json, text/event-stream）→ 200，serverInfo "Dify JWave Tools" 3.4.6
- `tools/list` → 200，工具列表正常
- 之前的 400（Authorization 头被拆行）不再出现

### 变更文件
- VM `~/dify-mcp-server/.env`（去重后 6 行）+ 备份 `.env.bak.20260817_125722`
- 本机 `docs/CHANGELOG.md`、`docs/HANDOFF_2026-08-17.md`（P1 标记已修复）

### 当前状态
- P1 ✅ 已修复；P2（2D均质初始压力 80%）、P3（DIFY_API_KEY 用途确认）、P4（nginx 0.0.0.0）待办
- 下个任务: P2 或按用户指示

## 2026-08-17 · 会话: T-007 多轮对话上下文记忆（网页端）

### 完成
- [x] T-007: 多轮对话上下文记忆。**实现方式与原方案不同**——原方案是改 Dify 工作流 conversation 变量，实际改为**网页端自管状态 + DeepSeek 合并**，不动已经调好的工作流和知识库
- [x] 门户页「声学仿真问答」区块改造为多轮聊天（气泡记录 + 🆕新对话 + 合并提示）
- [x] 新增独立全屏对话页 `/chat`（GET 页面 + POST 接口同路径），门户卡片区新增「💬 多轮对话」入口
- [x] 后端 `server_safe.py` 新增 `POST /chat` 路由 + `_merge_requirement()`（DeepSeek 合并历史需求）+ `_extract_report()`
- [x] 首轮直接当需求，后续轮次用 DeepSeek 把「历史需求 + 本轮修改」合并成完整需求再调工作流（合并失败自动降级拼接）
- [x] 新增可复用稳定性测试脚本 `test_multiturn_stability.py`
- [x] 环境修复：`executor/Dockerfile` 改用 Miniconda + conda-forge 从零构建 JAX（弃用缺失的 jwave-env.tar.gz）

### 变更文件
- `server_safe.py` — 新增 /chat 路由 + DeepSeek 需求合并 + 报告解析（顺带消除 /ask 重复解析）
- `dashboard.py` — PORTAL_HTML 多轮聊天 UI + 新增 CHAT_HTML 全屏对话页 + 门户卡片
- `test_multiturn_stability.py` — 新增多轮稳定性测试脚本
- `executor/Dockerfile` — Miniconda + conda-forge 从零构建 JAX 环境
- `compose.yaml` — 端口绑定 `192.168.30.200` → `0.0.0.0`
- `docs/CHANGELOG.md` `docs/AGENTS.md` `README.md` — 文档同步

### 测试结果
- 端到端：首轮"2 MHz 点声源"→ 成功（最大压力 0.4970，2403ms）；次轮"改成 5 MHz"→ DeepSeek 正确合并（最大压力 0.9771，2366ms）
- 稳定性：2 遍 × 7 轮 = 14 轮全部成功（100%），平均 27.8s/轮；连续 7 轮增量修改（改频率/网格/区域/加传感器/声速/时长）逐项精准累积、无参数漂移

### 踩坑
- 拿到 Dify API Key 后还需在 Dify 里点「发布」，否则 API 报 400 `Workflow not published`
- 容器偶发 `SSL: UNEXPECTED_EOF` 连不上 DeepSeek，系瞬时网络抖动（DeepSeek 可直连、不依赖 Clash），重试即恢复

### 当前状态
- 多轮对话已上线可用，成功率 100%
- 下个任务: 待定（候选 T-008 知识库扩展 / T-009 回归测试套件）

---

## 2026-08-08 · 会话: T-006 50次端到端测试 + p0 初始压力修复

### 完成
- [x] T-006: 50 次端到端回归测试完成，整体成功率 82% (41/50)
- [x] 根因分析：初始压力(p0)场景是最大短板，10 次仅成功 6 次
- [x] 诊断：LLM 不知道 `simulate_wave_propagation` 接受 `p0` 参数，错误地把高斯初始压力塞进 `Sources()` 导致全零
- [x] 修复：Dify 工作流代码生成 prompt 新增 p0 初始压力完整示例代码
- [x] 修复：`server_safe.py` 纠错速查表新增 3 条 p0 相关条目（p0 全零修复 / broadcast_shapes / 禁止空 signal）
- [x] p0 类别重测：6/10 → 9/10 (90%)
- [x] 修复 Dify draft 工作流 JSON 被 SQL 转义破坏的问题（恢复到 published 版本）

### 测试详情

| 类别 | 初测 | p0修复后 |
|------|------|---------|
| 2D均质点源 | 9/10 (90%) | — |
| 2D均质初始压力 | **6/10 (60%)** | **9/10 (90%)** |
| 2D异质介质 | 10/10 (100%) | — |
| 传感器记录 | 9/10 (90%) | — |
| 边界情况 | 7/10 (70%) | — |
| **总计** | **41/50 (82%)** | **~46/50 (92%)*** |

\* 估计值，含 p0 修复后的实际改善

### 已知剩余问题
- #36, #50: 仿真成功但 `np.save` 磁盘写入失败（sandbox 限制），非代码质量问题
- #3, #43, #46: 512×512 大网格超时，15s 不够
- p0 1 次失败（#7）：正则解析问题，实际仿真成功（732Pa）

### 变更文件
- `server_safe.py` — 纠错 Prompt 新增 p0/signal 速查项
- Dify 工作流 draft graph — 代码生成 prompt 新增 p0 示例（需要后续稳定修改）

### 当前状态
- 阶段一: T-001~T-005 ✅, T-006 82% (门禁 ≥90%)
- 阶段一门禁: 6/7 项通过，T-006 接近达标
- 下个任务: p0 prompt 稳定化 + 全量 50 次重测 → 打 `phase-1-complete` tag

---

## 2026-08-08 · 会话: T-005 Dify 工作流更新

### 完成
- [x] 在 Dify 工作流中插入 `validate_simulation_params` MCP 工具节点
- [x] 工作流从 8 节点变为 9 节点
- [x] 边重连: 参数提取 → validate_sim_params → 代码生成
- [x] 重启 Dify API + Worker 使变更生效

### 验证
- 校验工具正确拦截 Nyquist 违规（5MHz @ dx=1mm → 4 条 error）
- 合法参数正常放行（valid=true）

### 当前状态
- 阶段一任务: T-001~T-005 完成，T-006 待做
- 下个任务: T-006 (50 次端到端回归测试)

---

## 2026-08-08 · 会话: 文档体系建设

### 完成
- [x] 创建 `docs/` 目录
- [x] 编写 `PRD.md` v3.0 — 产品需求文档（人类评审版）
- [x] 编写 `AGENTS.md` v1.0 — Agent 指令手册（可执行任务队列）
- [x] 编写 `ARCHITECTURE.md` v1.0 — 技术方案与架构设计

### 当前状态
- 项目运行正常 (dify-mcp + jwave-executor)
- 成功率: 76% (26/34)
- 待修复: Sources 点源全零 (BUG-1)
- 下个任务: T-001 (排查 Sources 全零)

---

## 模板（每次会话后追加）

```
## YYYY-MM-DD · 会话: <主题>

### 完成
- [x] ...

### 变更文件
- `path/file.py` — <改动摘要>

### 测试结果
- ...

### 当前状态
- 成功率: XX%
- 下个任务: T-XXX
```
