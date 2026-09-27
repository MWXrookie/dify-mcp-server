# Codex Security 插件生产效果评估

## 结论

Codex Security 插件已安装并启用，MCP 服务可以启动，配置预检也返回 `ready`。但当前 MCP 探针不是 owning Codex thread，Standard 和 Prompt-only 两条扫描入口都拒绝创建扫描记录。因此本次没有伪造插件扫描成功，而是按用户要求记录精确错误，并使用插件预检、插件 MCP 能力发现和同等的只读审计流程完成人工审计。

生产价值判断：

- 对“桌面 Codex 原生入口”：值得继续测试；预检和工具面已可用。
- 对“当前任务内由父线程直接调用插件 MCP”：不可用；缺少 owning Codex thread context。
- 对本次安全目标：人工 fallback 仍有高价值，确认了 API Key 外泄、未授权管理接口和未来 skill store 信任边界问题。

## 环境与入口

已确认：

- `codex plugin list`：`codex-security@openai-api-curated` 状态为 `installed, enabled`。
- `codex mcp list`：`codex-security` MCP server 状态为 `enabled`，CLI 认证栏显示 `Unsupported`。
- 直接启动 `mcp/server.mjs --stdio` 成功。
- MCP `initialize` 返回服务名 `codex-security`，版本 `0.1.159`。
- MCP `tools/list` 成功，能够看到 Standard、Deep、draft、completion、workspace 等工具定义。

## 预检

第一次预检使用 `python`，命中 Windows Store 应用别名：

```text
Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app settings > App execution aliases.
```

这不是插件功能失败。改用机器上可用的 `py -3.12` 后，命令成功：

```text
py -3.12 <plugin>\scripts\config_preflight.py --profile security_scan --cwd <project> --runtime-check delegation_available=false
```

结果：

- `status`: `ready`
- `project_trust_level`: `trusted`
- `delegated_workers`: `fail` / `warn`，因为当前探针没有多 Agent delegation
- `usable_worker_slots_6`: `unknown` / `warn`
- `user_config_path`: `<local-workspace>`

解释：Standard Scan 没有子 Agent 时允许降级为父线程顺序审计。警告不阻断，但会降低并行调查和独立 baseline 的能力。

## 插件扫描入口

直接调用 `start_codex_security_standard_scan` 返回：

```text
Starting a Standard scan requires the owning Codex thread context.
```

直接调用 `start_codex_security_prompt_only_scan` 返回：

```text
Starting a prompt-only scan requires the owning Codex thread context.
```

评估：这两个错误是稳定、可复现的宿主上下文前置条件，不是认证失败、网络失败或 token 缺失。当前父线程能看到插件工具定义，但不能通过一个独立 MCP 子进程冒充 owning Codex thread。

## 实际执行的审计步骤

1. 读取插件入口 `plugin.json`、MCP 配置、capability profile、Standard 和 Deep 工作流说明。
2. 验证 MCP 服务可启动，并枚举扫描、draft、completion 工具。
3. 运行插件配置预检，确认 Standard profile 为可降级执行的 `ready`。
4. 无 Git diff，按固定源码快照审计。
5. 检查 MCP token 配置、custom route 鉴权、DeepSeek/Dify Key 数据流。
6. 检查 HTTP 出站目标是否由调用方控制，以及服务端 Key 是否可能随出站请求泄漏。
7. 检查 dashboard、cache、rerun、执行历史接口和浏览器渲染链。
8. 检查 executor 的容器配置、子进程环境、超时清理、网络、PID 和 `/tmp` 共享。
9. 检查 `.env`、`.gitignore`、`.dockerignore`、Dockerfile 和依赖锁定。
10. 检查 `work/plugin-tests/superpowers/skill_store.py` 的入库信任模型。
11. 运行语法编译检查；没有安装可用的 `bandit`、`semgrep`、`pip-audit`、`safety`、`trivy` 或 `osv-scanner`。

## 发现统计

- 高：2
- 中：3
- 低：2
- 合计：7

最重要发现：

- 任意 `base_url` 可导致服务端 DeepSeek Key 被发送到攻击者地址。
- MCP custom routes 没有鉴权，执行历史可读、可删，历史代码可被重跑。
- Markdown/HTML 渲染未净化，且 BYOK Key 保存在 `localStorage`。

## 人工复核与误报

人工复核结论：

- 未发现需要删除的误报。
- `SEC-05` 的运行时可达性低于其他发现，因此给出中等置信度；源码已显示同 UID、同 PID namespace、共享 `/tmp` 和仅 `killpg` 的清理边界。
- `SEC-06` 明确标注为现状加固缺口，因为当前 Dockerfile 使用选择性 `COPY`，没有证据显示 `.env` 已进入镜像。
- `SEC-07` 明确标注为供应链完整性风险，不声称具体依赖已有 CVE。

人工成本：

- 插件预检与入口验证成本低。
- 因为没有 owning-thread scan、没有 Git diff、也没有本机 SAST/依赖扫描器，关键结论全部依赖人工数据流追踪，人工成本中高。
- 如果没有 fallback，本次最关键的两条凭据/鉴权发现不会被插件自动产出。

## 建议

1. 在下一次任务中从 Codex 桌面或 CLI 的原生 owning thread 调用 `codex-security:security-scan`，而不是从父线程另起裸 MCP 子进程。
2. 再次测试时保留相同 user context，并确认生成的插件 `report.md` 产出与本次人工发现的一致性。
3. 在 Standard Scan 可用后，把它纳入发布前和合并前流程，而不是只跑一次 Demo。
4. 依赖漏洞扫描需要补充安装或接入独立扫描器；当前插件入口验证不能替代 SCA。
5. 对 `SEC-01` 和 `SEC-02` 应先修复再扩大服务网络暴露范围。

## 本次产物

- `docs/security/2026-09-23-codex-security-audit.md`
- `docs/security/2026-09-23-codex-security-plugin-evaluation.md`
