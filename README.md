# Dify FastMCP JWave Server

声学仿真 MCP 服务平台。Dify 工作流 → MCP 网关 → 沙箱执行器 → Markdown 报告。

## 部署架构

```
dify-mcp :8001 (FastMCP 网关 + Web 门户)
  ├── jwave-executor :8010 (隔离沙箱, 内网)
  ├── Dify nginx :80 (工作流引擎)
  └── DeepSeek API (纠错 + 代码修正)
```

两个容器：`dify-mcp` (Python 3.11-slim) + `jwave-executor` (Ubuntu 24.04, Conda jwave 0.2.1)。

## 快速命令

```bash
cd /home/wenxuan/dify-mcp-server
docker compose up -d --build          # 构建并启动
docker compose ps                      # 查看状态
docker restart docker-api-1 docker-worker-1  # MCP schema 刷新
```

## Web 门户路由

| 路由 | 页面 | 功能 |
|------|------|------|
| `/` `/portal` | 门户首页 | 导航卡片 + **声学仿真问答**（自然语言输入→Markdown 报告） |
| `/chat` | 多轮对话 | 全屏多轮对话：连续增量修改参数，自动合并需求并重新仿真 |
| `/dashboard` | 执行看板 | 实时执行记录、代码展开、图像预览、清空历史 |
| `/report` | 测试报告 | T-006 成功率、场景分类、失败分析、时间线 |
| `/cache` | 纠错缓存 | 经验条目、命中率、置信度分布、高频经验 |
| `/demo` | Demo 演示 | 6 个预设声学场景一键运行 |
| `/health` | 健康检查 | 网关存活检测 |

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/ask` | POST | 门户问答代理 → Dify 工作流（返回 Markdown 报告） |
| `/chat` | POST | 多轮对话代理：合并历史需求 → Dify 工作流（返回报告 + 完整需求） |
| `/dashboard/api/executions` | GET | 执行历史（分页） |
| `/dashboard/api/executions` | DELETE | 清空执行历史 |
| `/dashboard/api/test_report` | GET | 最新测试报告 JSON |
| `/dashboard/api/cache_stats` | GET | 纠错缓存统计 JSON |
| `/demo/api/run` | POST | Demo 页代理 → Dify 工作流 |

## MCP 工具

| 工具 | 说明 |
|------|------|
| `run_jwave_code` | 执行 Python 代码（1-30s 超时, 20KB 上限） |
| `run_jwave_code_with_retry` | 执行 + DeepSeek 自动纠错 + 重试（≤7 次）+ **自动生成 Markdown 报告** |
| `validate_simulation_params` | 硬编码物理规则校验（Nyquist/CFL/网格/PML） |
| `jwave_environment` | 执行器环境健康检查 |
| `list_installed_libraries` | 已安装工具列表 |

## 数据存储

- SQLite `/app/data/execution_history.db` — 执行记录（volumes 持久化）
- SQLite `/app/data/error_cache.db` — 纠错经验缓存（volumes 持久化）
- 测试报告 `docs/test_results_raw*.json` — 通过 docs 目录挂载自动同步

## Dify 工作流配置

- MCP URL: `http://dify-mcp:8001/mcp`
- Auth: `Authorization: Bearer <MCP_AUTH_TOKEN>`
- SSRF 白名单: `SSRF_PROXY_ALLOW_PRIVATE_DOMAINS=dify-mcp`
- 工作流末尾：MCP retry → **代码节点**（提取 report 字段）→ 结束节点输出 Markdown

### 代码节点配置

```python
import json

def main(mcp_json):
    data = mcp_json
    if isinstance(data, list) and len(data) > 0:
        data = data[0]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return {"result": data}
    if not isinstance(data, dict):
        return {"result": str(data)}
    report = data.get("report", "")
    if report:
        return {"result": report}
    return {"result": json.dumps(data, ensure_ascii=False, indent=2)}
```

输出变量：`result`。结束节点引用：`{{代码节点.result}}`。

## 当前状态（2026-08-09）

- 所有路由 200 OK
- Dify 工作流通畅，返回 Markdown 报告
- 门户问答功能正常
- T-006 最新测试：**50 次, 48 成功, 96.0%**
- 纠错缓存：12 条经验, 27 次命中, 88.9% 成功率
- 执行看板：31 条记录, 30 成功, 1 失败
- 看板图像列已修复（每个仿真独立保存图片）
- 缓存置信度逻辑已修复（正确升降级+退役机制）
- 执行看板已精简为 5 列（去掉工具列, 代码摘要智能跳过 import）

## 环境变量

```bash
MCP_AUTH_TOKEN=<32+ 字符>
EXECUTOR_SHARED_TOKEN=<32+ 字符>
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_MODEL=deepseek-chat
CODE_RETRY_MAX=7
```

## 备份

```bash
ls /home/wenxuan/dify-mcp-server/.claude/backups/
```

## 关键技术细节

- jwave 0.2.1 正确 API（非 LLM 编造）: `TimeAxis.from_medium()`, `.to_array()`, `FourierSeries(data, domain)`, `Sources(positions, signals, dt, domain)`
- 代码自动修正: `.max()` → `jnp.max(jnp.abs())`, `.params[0]` → `.params`, `plt.savefig('/tmp/result.png')` → `plt.savefig('result.png')`
- Executor 沙箱: read_only rootfs, cap_drop ALL, no-new-privileges, pids_limit 256, mem_limit 4g, tmpfs /tmp
