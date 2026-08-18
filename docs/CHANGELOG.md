# 变更日志

> 记录每次开发会话的变更，按时间倒序。

---

## 2026-08-18 · 会话: T-014 Dashboard 失败分析区块（乙）

### 完成
- [x] T-014 失败分析面板：看板新增「失败分析」区块，失败记录按类型归类（⏱ 超时 / ❌ 退出码非0 / ⚠️ 结果异常全零）三组展示
- [x] 点击失败记录展开详情（复用表格 detail-row，自动滚动定位）
- [x] 复用现有深色 GitHub 风格，无失败记录时自动隐藏面板

### 变更文件
- `docs/dashboard.html` — 新增失败分析面板（CSS + HTML 结构 + classifyFailure/renderFailAnalysis JS）

### 验证
- 本机 `http://localhost:8001/dashboard` 返回 200，新内容（失败分析/fail-analysis/renderFailAnalysis）全部生效
- JS 括号平衡检查通过，HTML div 平衡通过
- 现有 23 条记录中 1 条「退出码非0」被正确归类

### 当前状态
- T-014 失败分析区块完成；待 VM 部署验证（合并后由甲 pull + 重建）

---

## 2026-08-18 · 会话: 产品清理 + P0 增强（会话隔离 / 进度反馈 / 看板对比）

### 清除多余部分（6 项）
- 删除 `run_allowlisted_tool` MCP 工具 + `library_tools.py`（白名单仅含无关的 slugify）+ `python-slugify` 依赖（MCP 工具 7→6）
- 删除 `server_exec.py`（无引用的旧变体）、`requirements.code.txt`（冗余一行）、`dashboard.py` 空占位 `DASHBOARD_HTML`
- 归档旧测试产物到 `docs/archive/`：`run_50_tests_legacy.py`、`test_report_phase1_new.md`、`test_results_raw*.json`
- 同步：Dockerfile COPY、`list_installed_libraries` 移除 allowlisted_tools 字段

### P0-1 多轮对话上下文隔离
- `/chat` 前端生成持久化 `session_id`（localStorage），随请求发送；后端按会话区分 Dify `user`（`portal-<session>`）
- 为 T-011 多轮记忆（Dify conversation）铺路：不同会话不再共享 Dify 用户上下文

### P0-2 仿真进度反馈
- 门户 + 多轮对话等待提示增强："正在执行仿真（生成代码 → 沙箱计算 → 物理分析），通常需要 30~90 秒"
- （真流式 SSE 成本较高，记为后续项，blocking 模式加提示过渡）

### P0-3 看板结果对比
- `docs/dashboard.html` 新增对比列：勾选两条执行记录 → 对比面板展示 工具/状态/耗时/尝试次数/最大压力/图像
- 数据复用 executions API（stdout 正则提取最大压力）

### 变更文件
- `tools.py`、`portal.py`（session 隔离）、`dashboard.py`（getSessionId + 等待提示，两处 JS）、`docs/dashboard.html`（对比）、`Dockerfile`、`requirements.lock.txt`
- 删除：`library_tools.py` `server_exec.py` `requirements.code.txt`
- 归档：`docs/archive/*`

### 验证
- MCP 工具 6 个 ✓；portal/chat/dashboard 200 ✓
- /chat 带 session_id 正常（requirement 回传正确；failed 为 embedding 网络抖动）
- 看板对比功能上线（页面含 compare-panel）

### 当前状态
- 阶段二 ✅ + P2 ✅ + 可视化 ✅ + 清理 ✅ + P0 三项 ✅；待打 `phase-2-complete` tag

---

## 2026-08-18 · 会话: 仿真热力图可视化落地（每次仿真出图）

### 背景
- 之前 analyze 每次仿真都生成热力图（base64），但只在工作流内部变量里，用户不可见；看板图像又依赖 LLM 画图（多数没有）→ "可视化"承诺未兑现

### 完成
- [x] **报告嵌入热力图**：工作流合并节点（MERGE1/MERGE2）解析 analyze 输出，把 `heatmap_png_base64` 转成 `![压力场热力图](data:image/png;base64,…)` 追加到报告 → 门户/多轮对话 Markdown 直接显示
- [x] **看板存图**：`analyze_simulation_result` 工具把热力图写入执行记录（`record_execution`，image_base64）→ 看板每次仿真都有图
- [x] 修复 MERGE2 重试解读解析 bug（Dify json 变量嵌套 list/data 包裹，`_find_analyze` 健壮解析）
- [x] 脚本链（可复现）：`_build_graph.py` → `_build_t009.py` → `_apply_p2_prompt.py` → `_apply_heatmap.py`

### 验证（真实端到端）
- /ask 报告：含热力图 Markdown（PNG base64 魔数 iVBORw0KGgo ✓）+ 物理解读
- 看板：`analyze_simulation_result | 图: 有 | 25488`（每次仿真必出）

### 变更文件
- `analysis.py`（analyze 工具写入看板）、`_apply_heatmap.py`（工作流合并节点更新脚本）
- 工作流 graph（合并节点，备份见 `docs/dify_workflow_backup/live_heatmap_*`）
- 文档：`docs/CHANGELOG.md`

### 当前状态
- 阶段二全部 ✅ + P2 ✅ + 可视化 ✅；待打 `phase-2-complete` tag

---

## 2026-08-18 · 会话: P2 修复「2D均质初始压力 80%」→ 100%

### 根因（阶段一遗留，50 次测试 2 失败）
1. **环形初始压力全零**（#16）：LLM 无 p0 正确参考，环形场构造错误/被 PML 吸收
2. **参数名写错**（#17）：`simulate_wave_propagation() got an unexpected keyword argument 'initi…'`，重试 8 次失败
3. **关键发现**：工作流代码生成 prompt 中**完全没有 p0 内容**（此前"修复"未进工作流）——LLM 只能瞎猜参数

### 修复（三处）
1. **`tools.py` validate_simulation_params 新增第 8 项 initial_pressure 校验**：类型白名单（gaussian/ring/circle/ellipse/plane）、peak>0、**环形半径/椭圆半轴 ≥ 域半宽 → 拦截**（几何超域 → 场被 PML 吃掉 → 全零）
2. **`llm.py` 纠错速查表新增 p0 条目**：参数名只能是 p0（不存在 initial_pressure=）；环形/椭圆 p0 的 meshgrid 正确构造示例
3. **工作流代码生成 prompt 追加 p0 完整示例**（`_apply_p2_prompt.py` 幂等注入）：高斯/环形/椭圆三种 p0_grid 构造 + "参数名是 p0" 警告

### 验证（真实端到端）
- P0 初始压力 4 场景（高斯/环形/椭圆/p0）：**4/4 成功（100%）**
- 环形场景实测 max_pressure=1396 Pa（非全零，含物理解读）
- 校验工具：环形半径 0.1m 超域（域半宽 0.0512m）→ 正确拦截；合法环形 → 无 p0 错误

### 变更文件
- `tools.py`（校验规则 8）、`llm.py`（速查表）、`_apply_p2_prompt.py`（prompt 注入脚本，可复现）
- 工作流 graph（代码生成 prompt，备份见 `docs/dify_workflow_backup/`）
- 文档：`docs/AGENTS.md`、`docs/DEVELOPMENT_PLAN.md`

### 当前状态
- 阶段二全部 ✅（VAL-1/T-007/T-008/T-009/多轮对话）+ **P2 遗留 ✅（初始压力 100%）**
- 待办：打 `phase-2-complete` tag → 阶段三（T-013 知识库扩展等）

---

## 2026-08-18 · 会话: T-009 迭代循环完成 + 修复 executor 硬编码 python 路径

### T-009 迭代循环（Dify 工作流 13 → 21 节点，预展开方案）
- 从 Dify 3.x 源码（graphon 包）确认 if-else 新版 schema：`cases[].case_id` + `"false"` ELSE 分支（非网传老结构）
- **回边实验否决**：审查→参数提取回边虽被 graph 校验接受，但执行被破坏（后续节点全不执行、run 误报 succeeded）→ 采用**静态预展开**（2 次尝试：首次 + 1 次参数级重试，天然保证终止）
- 新增：if-else 分支 + 参数提取2（prompt 注入审查建议）+ 代码生成2 + MCP retry2 + 解包2 + analyze2 + 合并2 + end2
- 审查节点 prompt 增强：max_pressure 极小（<0.001 Pa）即使 verdict=normal 也应 retry

### 验证（真实端到端）
- ✅ 正常场景（96×96）：if-else 选 `pass` 分支，完整报告 + 物理解读
- ✅ 异常场景（10MHz @ dx 0.5mm 欠采样，max_pressure≈0.0001）：审查判 retry → if-else 选 `false` → **重试链 5 节点全部执行** → 输出"已自动重试一次" → 2 次尝试后正确终止

### 重要修复：executor.py 硬编码 python 路径（环境切换遗留 bug）
- 症状：executor 对所有请求 400，`No such file or directory: '/opt/jwave/bin/python'`
- 根因：纯 pip 环境 python 在 `/usr/local/bin/python`，executor.py 仍硬编码旧 conda 路径 `/opt/jwave/bin/python`（7fb0251 环境切换时漏改）
- 修复：改用 `sys.executable`（环境无关，conda/pip 均兼容）；**此 bug 曾导致所有工作流仿真静默失败**
- 验证：executor 直接执行 200 + python 路径正确

### 变更文件
- `executor/executor.py`（python 路径修复）
- `_build_t009.py`（T-009 工作流构造脚本，可复现）
- `docs/dify_workflow_backup/live_t009_before_review_enhance_*.json`（改造前备份）
- 文档：`docs/AGENTS.md`、`docs/DEVELOPMENT_PLAN.md`

### 当前状态
- 阶段二：VAL-1 ✅ T-007 ✅ T-008 ✅ **T-009 ✅（迭代循环，2 次尝试正确终止）**；多轮对话 ✅（组员，93%）
- 阶段二门禁全部达成 → 待 Owner 确认后打 `phase-2-complete` tag

---

## 2026-08-18 · 会话: git 历史重写——彻底清除泄露内容（⚠️ 所有 commit hash 已变更）

### 背景
- 仓库公开且历史含敏感内容（.claude 私有备份目录、AGENTS.md 明文 MCP token、旧代码硬编码 app key）
- 前次已轮换密钥 + 清理当前快照；本次**重写全历史**彻底清除

### 执行（git-filter-repo 2.47）
1. 在 fresh clone 上 `--invert-paths --path .claude`（删除私有备份目录，历史中全部移除）
2. `--blob-callback` 替换明文凭证（完整 token、app key、以及前 8 位截断）为 `***REMOVED***` 占位
3. 验证：全历史含 MCP token / Dify app key / `.claude` 均为 **0**；commit 数不变（35）
4. force push：main `fe44f5b → 850680d`、tag `phase-1-complete` 已重写推送、**feat/multiturn-chat 分支已删除**

### ⚠️ 影响与后续
- **所有 commit hash 已变**：任何本地仓库需 `git fetch origin && git reset --hard origin/main`
- **GitHub PR #1 仍指向旧 commit**：需在 GitHub UI 关闭（命令行无法操作）
- fork 副本/旧 commit 的 GitHub 缓存无法控制（随 GC 自然失效），密钥已轮换故泄露值已失效
- VM 原仓库已 `git reset --hard origin/main` 切换完成，.env 等未跟踪文件不受影响

---

## 2026-08-18 · 会话: 安全处置——仓库敏感内容清理 + 双密钥轮换

### 背景
- 审查发现公开仓库存在真实凭证泄露：AGENTS.md 明文 MCP Bearer token（与线上一致）；`.claude/backups/` 内旧代码硬编码 Dify app key（查 DB 确认仍有效）

### 完成
- [x] **轮换 MCP_AUTH_TOKEN**：新 64 位 hex（`b7ff717f…`）
  - 更新 VM `.env` + Dify `tool_mcp_providers.encrypted_headers`（用 Dify `encrypt_token` 加密，明文格式 `Bearer <token>`）
  - 重建 dify-mcp；验证：新 token 通（7 工具）、**旧 token 401**、工作流端到端 succeeded
- [x] **轮换 Dify app key**：旧 key → 新 `app-9d44dd0c79…`（api_tokens 表 + VM `.env` 同步）
- [x] **仓库清理**：`git rm --cached -r .claude`（8 文件、-6406 行）；`.gitignore` 加 `.claude/`；AGENTS.md 删除明文 token（改指向 VM `.env`）
- [x] 备份：`.env.bak.rotate_20260818_070432` + Dify 表 dump（api_tokens/tool_mcp_providers）

### 待办（需 Owner 决策）
- ⚠️ **git 历史仍含泄露内容**（历史 commit 里有 .claude 备份与 AGENTS.md 明文 token）。若仓库完全公开且在意，需 `git filter-repo` 重写历史（会改变所有 commit hash，影响组员本地仓库，需协商后执行）
- 旧 `.env.bak.*`、`.claude/` 备份文件保留在 VM 本地（不进仓库）

### 变更文件
- `.gitignore`（+`.claude/`、`test_multiturn_result.json`）、`docs/AGENTS.md`（删明文 token）

---

## 2026-08-18 · 会话: executor 环境切换（纯 pip 方案，验证后采纳）

### 背景
- 组员 07fcdc2 将 executor 改为 Miniconda 从零构建（jax 0.4.35）；用户担心影响，走"验证后采纳"路径
- 实测发现**纯 pip 方案可行且更优**（组员"PyPI 不匹配"说法未复现），无需 Miniconda

### 验证过程（全程不碰运行中的旧容器）
1. 临时容器实测纯 pip：jax[cpu]==0.4.35 + numpy 1.26.4 + scipy + matplotlib + jwave 0.2.1（--no-deps）+ jaxdf/equinox/jaxtyping/plum 等 → 装通、import 正常
   - 修正：jaxdf 等**不能 --no-deps**（会缺 typing_extensions 等传递依赖），仅 jwave 用 --no-deps
2. 构建验证镜像 `local/dify-mcp:jwave-pip-verify`：**30s**、1.65GB（旧 tarball 镜像 4.22GB）
3. **VAL-1 基准在新镜像 3/3 PASS，误差与旧环境逐项一致**（用例1 0.0002% / 用例2 0.80% / 用例3 0.003%+0.002%）→ 物理等价

### 决策与执行
- `executor/Dockerfile` 正式切换为纯 pip 版（v1 tarball → v2 miniconda → **v3 纯 pip**，沿革写入 Dockerfile 注释）
- `docker compose up -d --build jwave-executor` 切换运行容器
- 验证：容器健康（jax 0.4.38 / numpy 1.26.4 / jwave import OK）；真实工作流 succeeded 含物理解读
- 旧环境可回滚：git 旧 Dockerfile + VM `executor/jwave-env.tar.gz` 仍在

### 收益
- 构建 10-30min（miniconda）→ **30s**；镜像 4.22GB → **1.65GB**；版本透明可复现；物理结果不变
- 顺带修掉旧环境潜在隐患（jax 0.4.30 + numpy 2.5.1 属未适配组合 → 现为官方匹配的 jax 0.4.35 + numpy 1.26）

### 变更文件
- `executor/Dockerfile`（纯 pip 版，含 v1/v2/v3 沿革注释）

### 当前状态
- 阶段二：VAL-1 ✅ T-007 ✅ T-008 ✅ 多轮对话 ✅（93%）；**executor 环境 ✅ 已切纯 pip**
- 待办：T-009（迭代循环）；embedding API 抖动需关注（今日已 4 次，知识检索节点随缘失败，建议排查 tongyi key/网络）

---

## 2026-08-18 · 会话: 消化组员多轮对话提交（07fcdc2）+ 修复场数据超限

### 组员提交内容（已消化上线）
- [x] **/chat 多轮对话**（portal.py：GET 页面 + POST 代理，DeepSeek 需求合并）：已部署，实测 merge_used 生效、增量改参正确（2MHz→3MHz 其余保留）
- [x] **dashboard.py 增强**（+302 行 HTML）与 **test_multiturn_stability.py**（14 轮稳定性测试）
- [x] README 更新（/chat 路由文档）
- ⚠️ **compose.yaml 端口改 0.0.0.0**（已部署生效）：MCP 网关暴露到所有网卡，有 64 位 Bearer token 保护；如 VM 有公网 IP 需评估（同 P4）
- ⚠️ **executor/Dockerfile 改用 Miniconda 从零构建**（jax 0.4.35 / numpy 1.26 等）：**未部署**（保持旧 tarball 环境运行），代码保留在仓库，待"验证后采纳"决策

### 实测发现并修复（本次核心价值）
- 组员稳定性测试实测 **57%**（14 轮 8 成功），与提交说明"14/14"不符
- **根因（我 T-008 引入）**：场数据输出模板在大网格（≥256×256）时 JSON 超 Dify 变量上限
  `The length of output variable stdout must be less than 400000 characters`
- **修复（双保险）**：
  1. `execution.py` 新增 `_shrink_field_in_stdout`：网关层强制压缩场 JSON（降采样 + 保留全场 max_pressure），**不依赖 LLM 自觉**；接入 run_jwave_code / retry 两个工具
  2. 场输出模板（analysis.FIELD_OUTPUT_SNIPPET + 工作流代码生成 prompt）加自适应降采样
  3. analysis 支持 payload.max_pressure 覆盖（降采样不丢峰值量级）
- 修复后重测：**92.9%（13/14）**，唯一失败为 embedding API 网络抖动（重试即过，非功能问题）

### 变更文件
- `execution.py`（+_shrink_field_in_stdout）、`tools.py`（接入压缩）、`analysis.py`（降采样模板+max_pressure 覆盖）、`_build_graph.py`（新场输出指令）
- `docs/dify_workflow_backup/live_after_shrinkfix_*.json`（修复后 graph 备份）

### 当前状态
- 阶段二：VAL-1 ✅ T-007 ✅ T-008 ✅；**组员多轮对话已上线（实测 93%）**
- 待决策：executor 环境切换（"验证后采纳"路径：单独构建新镜像 + VAL-1 回归）
- 下个任务: T-009（迭代循环）或按用户指示

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
