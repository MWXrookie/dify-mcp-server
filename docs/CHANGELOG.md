# 变更日志

> 记录每次开发会话的变更，按时间倒序。

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
