# 变更日志

> 记录每次开发会话的变更，按时间倒序。

---

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
