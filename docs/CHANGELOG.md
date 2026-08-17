# 变更日志

> 记录每次开发会话的变更，按时间倒序。

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
