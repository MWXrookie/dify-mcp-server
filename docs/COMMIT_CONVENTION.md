# 提交规范（COMMIT_CONVENTION）

> **本文件是提交代码的强制要求。每次 `git commit` 前必须阅读并逐项对照检查清单。**
> 适用对象：所有成员（Owner / 组员 / AI Agent）。不遵守规范 = 提交被拒，要求返工。

---

## 1. 提交信息格式（必须）

```
<type>: <scope> <subject> — <detail>
```

示例（来自本仓库真实提交）：

```
refactor: 网关模块化拆分 — server_safe.py 1074行薄壳化(约60行) + 7模块(config/cache_store/execution/llm/tools/portal/analysis), T-007落点 analysis.py; 行为零变更, VM 已部署验证
fix: 消化组员多轮对话提交 — 实测57%→93%（场数据超Dify 40万字符变量上限）；网关层强制压缩场JSON
security: 仓库清理 + 密钥轮换 — 移除 .claude 私有备份目录; AGENTS.md 删除明文 MCP Bearer token
chore: 仓库去私人化/可移植化 — 脚本改相对路径+GW_BASE_URL环境变量; 文档脱敏
docs: CHANGELOG 记录安全轮换与仓库清理
```

### 1.1 type（必填，小写）

| type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修 bug |
| `refactor` | 重构（行为不变） |
| `docs` | 文档 |
| `chore` | 杂务（构建/配置/去私人化等） |
| `security` | 安全修复/密钥轮换/清理 |
| `revert` | 回滚 |
| `test` | 测试 |
| `perf` | 性能 |

### 1.2 scope（可选但有就用）

受影响模块：`网关` / `executor` / `工作流` / `analysis` / `portal` / `dashboard` / `测试` / `部署` / `docs` / `环境` 等。任务编号（T-XXX / VAL-1）可放 scope 或 subject 开头。

### 1.3 subject + detail

- **subject**：一句话说清"做了什么"（中文，动词开头）
- **detail**（`—` 后）：补充关键信息：原因、影响面、验证结果、破环性变更。**有验证就写验证结果**（如"实测 93%"、"VAL-1 3/3 PASS"）

### 1.4 提交信息红线

- ❌ 空提交信息 / 只有"update"、"fix bug"这类无信息量标题
- ❌ 提交信息里写**密钥/Token 明文**（含前 N 位截断！历史重写教训）
- ❌ 把多个不相关改动塞进一个提交（应拆多个 commit）

---

## 2. 提交前检查清单（每次 commit 前逐项过）

### 2.1 安全红线（最高优先级，违反即事故）

- [ ] `.env` / `.env.bak.*` / `*.log` / `__pycache__/` / `*.tar.gz`（含 `executor/jwave-env.tar.gz`）**绝不提交**（已在 .gitignore，但 commit 前确认 `git status` 无此类文件）
- [ ] 提交内容中**无任何密钥/Token 明文**（MCP token、Dify app key、DeepSeek key、密码）
- [ ] 无 `.claude/` 等本地工具目录
- [ ] 无本地绝对路径（`/home/<用户名>/...`、`C:\Users\<用户名>\...`）、SSH 别名、密钥文件名
- [ ] 测试运行产物（如 `test_multiturn_result.json`）不提交

### 2.2 质量红线

- [ ] 改动的 Python 文件通过语法检查：`python3 -m py_compile <改动文件>`
- [ ] 改 Dify 工作流 → 已备份 graph 到 `docs/dify_workflow_backup/` 并提交
- [ ] 改了 executor/Dify 环境 → 附验证结果（如 VAL-1 回归、工作流端到端）
- [ ] 功能改动 → 有实际验证（真实调用/测试），验证结果写进 commit detail

### 2.3 流程

```bash
git status                 # ① 确认无敏感/多余文件
git add <明确文件清单>      # ② 显式 add，不用 git add -A 偷懒（防误加）
git commit -m '<type>: <scope> <subject> — <detail>'   # ③ 按第 1 节格式
git push origin main       # ④ 推送
```

---

## 3. 分支与 PR 规范

- **主分支 `main`**：始终可部署。直接向 main 提交（小团队）或走 PR 均可，但 main 上**不允许破坏性提交**（schema 变更、环境切换必须带验证）
- **功能分支**：命名 `feat/<描述>` 或 `fix/<描述>`（如 `feat/multiturn-chat`）
- **合并到 main**：合并后**必须在 VM 部署验证**（`git pull` + `docker compose up -d --build`），验证结果写入合并 commit 或 CHANGELOG
- **历史重写**：除非安全需要，**禁止** `git push --force`（会改变所有 commit hash，影响全体成员；确需时先通知所有成员同步，参照 2026-08-18 密钥轮换先例）

---

## 4. 会话纪律（铁律）

1. **每次会话结束必须提交**：不留未提交工作过夜（否则下次接不上、历史断裂）
2. **每个任务一个提交**：小步提交，便于回滚（`git log --oneline` 应能看懂任务脉络）
3. **改了什么 → 写进 CHANGELOG.md**（追加到最上方，格式见文件内模板）+ AGENTS.md 任务状态同步
4. **提交信息与 CHANGELOG 一致**：两者描述的是同一件事

---

## 5. 可移植性红线（2026-08-18 新增，吸取教训）

- 代码里**不得硬编码**：本机绝对路径、用户名、内网 IP、SSH 配置
- 需要配置的用环境变量：网关地址 `GW_BASE_URL`、端口绑定 `DIFY_MCP_BIND_IP`、API key 一律从 `.env` 读
- 文档里的 IP/路径视为**示例**，标注"按你的环境替换"

---

## 6. 快速自查（commit 前 10 秒）

```bash
git status --short                        # 有 .env/*.log/*.tar.gz/.claude 吗？
grep -rIn 'sk-\|app-[0-9a-f]\{20,\}\|Bearer: [0-9a-f]\{20,\}' <本次改动文件>   # 有密钥吗？
git diff --cached --stat                  # 改动范围符合预期吗？
```

---

*更新记录：2026-08-18 创建（结合项目提交历史、密钥轮换/历史重写/去私人化三次事故的教训）。*
