# 项目经验文档 — Bug 修复与避坑记录

本项目在开发过程中遇到多种问题，涉及 jwave API、Dify 集成、MCP 网关、看板前端等多个层面。这份文档记录关键问题和修复方案，作为团队知识沉淀。

---

## 1. 纠错缓存置信度失效

**现象**：纠错缓存始终为空，即使执行了大量 retry，缓存面板显示"暂无经验"。

**根因**（多处叠加）：
1. `_query_cache()` 中取 confidence 字段下标错误，用了 `row[5]` 实际是 `row[6]`，导致返回的 confidence 永远为 0，达不到 0.7 门槛。
2. `_update_cache()` 中 `datetime.now(timezone.utc)` 报 `NameError`，因为顶部缺少 `from datetime import datetime, timezone`。
3. `run_jwave_code_with_retry` 每次调 `_update_cache(was_successful=False)`，即使 LLM 修复后重试成功了也没更新为成功状态，置信度始终偏低。
4. `_cache_db()` 未设置 `row_factory = sqlite3.Row`，导致数字下标访问不安全。

**修复**：
- 修正字段下标为 `row[6]`
- 顶部补上 `from datetime import datetime, timezone`
- 增加 `last_error_sig` 跟踪，重试成功后调 `_update_cache(was_successful=True)`，重试耗尽才标记失败
- `_cache_db()` 加上 `db.row_factory = _sql.Row`

**教训**：缓存系统的核心逻辑（成功/失败标记、置信度升降级、退役机制）需要单元测试覆盖，不能只靠端到端验证。

---

## 2. 仿真图像全部相同（串图问题）

**现象**：看板执行历史中，不同仿真的缩略图完全一样。

**根因**：
1. `_clean_code()` 自动注入 `plt.savefig('/tmp/result.png')`，写到了共享路径
2. `executor.py` 中先检查 workdir 的图，没有则回退读 `/tmp/result.png`，导致上一个任务的旧图被后续任务读到

**修复**：
- 自动注入改为 `plt.savefig('result.png')`（写到当前 workdir）
- executor 删除 `/tmp/result.png` 回退读取逻辑，只读 workdir 的图

**教训**：临时文件路径必须是每个请求隔离的，共享路径会导致数据污染。这条在 Docker 的 tmpfs 环境下尤其容易出问题。

---

## 3. Dify 工作流输出格式变更导致 Demo 页大量报错

**现象**：Demo 页运行场景后，卡片显示"失败"，JS 控制台大量报错。

**根因**：Dify 工作流增加了代码节点后，结束节点输出从原来的 dict（含 `exit_code`, `stdout` 等字段）变成了**纯 Markdown 字符串**。但 Demo 页的 JS 仍用旧逻辑解析 `o.exit_code`、`o.timed_out` 等字段，全部变成 undefined。

**修复**：重写 `runScenario()` 函数，改为：
- 从 Markdown 文本中匹配 `✅ **成功**` / `❌ **失败**` 判断状态
- 用正则提取最大压力、耗时、尝试次数
- 将报告文本直接格式化展示

**教训**：API 输出格式变更时，必须检查所有消费者（Demo 页、门户问答、看板等），不能只改一处。

---

## 4. 门户问答 `/ask` API 返回空结果

**现象**：门户页输入声学问题后，结果区域显示"(工作流返回空结果)"。

**根因**：`/ask` 路由的解析逻辑有两层问题：
1. 旧代码把 Dify 返回的 `outputs.text` 当成 dict 处理（`o.get("result")`），但实际上 Dify 返回的是**纯字符串**
2. Docker 镜像缓存导致修改后的代码未进入容器，`docker compose up -d --force-recreate` 不会重新 build，需要 `--build` 或 `--no-cache`

**修复**：
- 改写 `/ask` 解析逻辑，优先处理字符串类型
- 用 `docker compose build --no-cache` 强制重建镜像

**教训**：Docker 缓存机制在频繁修改时需要特别关注；`--force-recreate` ≠ 重新构建镜像。

---

## 5. 测试报告页面无法显示最新数据

**现象**：看板测试分析页显示的仍是旧数据（82%），而不是新跑出来的 96%。

**根因**（两处）：
1. `load_test_results()` 只读 `test_results_raw.json`（旧文件），没有读 `test_results_raw_new.json`（新文件）
2. 容器内的 `/app/docs` 没有挂载宿主机目录，新生成的文件无法自动同步
3. 新文件格式是 `{"results":[...]}` dict，旧逻辑只认纯 list

**修复**：
- `TEST_RESULTS_PATHS` 增加 `test_results_raw_new.json`
- `_find_test_results()` 改为取最近修改时间的文件
- `load_test_results()` 增加 dict 格式的解析分支
- `compose.yaml` 添加 `./docs:/app/docs:ro` 挂载

**教训**：文件同步方案中，volumes 挂载比 COPY 更适合频繁变动的数据。

---

## 6. 看板表格列冗余 + 代码摘要不区分

**现象**：
- "工具"列每行都是 `run_jwave_code_with_retry`，完全冗余
- "代码"列截断 60 字符，所有代码开头都是 `import jax\nimport jax.numpy...`，看不出区别

**修复**：
- 删除"工具"列和"图像"列（图像改为状态圆点）
- 新增 `smartSummary()` 函数，跳过 import 前缀行，直接显示第一条有意义的代码
- 代码截断延长到 100 字符
- 表格从 7 列精简为 5 列

**教训**：前端数据展示要紧跟实际数据特征。当数据源的结构固定（如 MCP 工具名永远相同），硬编码的列就是噪音。

---

## 7. 门户页面功能重叠

**现象**：
- 执行看板里嵌了"测试分析"标签页，门户又有独立的"测试报告"和"测试分析"卡片
- 门户有"测试报告 API"和"纠错缓存 API"两张卡片指向裸 JSON
- 功能入口散乱，用户体验差

**修复**：
- 执行看板去掉测试分析标签，改为独立 `/report` 页面
- 门户合并重复卡片，所有入口指向独立渲染页面（/dashboard, /report, /cache, /demo）
- API 裸输出改为独立 HTML 页面

**教训**：在增加功能时，要定期审视整体路由结构，避免同质页面堆积。

---

## 8. MCP 工具输出字段在 Dify 中不可选

**现象**：MCP 工具返回的 dict 字段（如 `report`）在 Dify LLM 节点的变量选择器中不可见，只能看到 `text`、`files`、`json`。

**根因**：Dify 的 MCP 集成会把工具返回值包在 `text` 字段中，LLM 节点只能引用字符串类型的变量，无法直接展开 dict。

**解决方案**：在 MCP 工具和结束节点之间插入**代码节点**，用 Python 从 `json` 字段中提取 `report` 字符串：

```python
import json

def main(mcp_json):
    data = mcp_json
    if isinstance(data, list) and len(data) > 0:
        data = data[0]
    if isinstance(data, str):
        data = json.loads(data)
    report = data.get("report", "")
    return {"result": report} if report else {"result": str(data)}
```

**教训**：Dify 的 MCP 集成在处理复杂返回值时有局限，代码节点是弥补这一短板的关键工具。

---

## 9. `/demo/api/run` 代理路由阻塞问题

**现象**：Demo 页调用 Dify 工作流时，偶发性卡死，浏览器报超时。

**根因**：`/demo/api/run` 路由用同步 `httpx.post` 调用 Dify nginx，在 `async def` 路由函数中阻塞了事件循环。

**修复**：改为 `async with httpx.AsyncClient(timeout=130) as client`。

**教训**：asyncio 路由函数中绝对不能使用同步 HTTP 客户端，会导致整个服务阻塞。

---

## 10. 浏览器缓存导致页面未更新

**现象**：多次部署后，用户反馈"页面没变化"，但服务端确认已更新。

**根因**：浏览器对 HTML/CSS/JS 做了强缓存，普通刷新（F5）不生效。

**修复方案**（推荐给用户）：
- `Ctrl + Shift + R`（强制刷新，跳过缓存）
- 开无痕窗口访问
- 在地址栏加 `?v=1` 参数破坏缓存

**教训**：生产环境中应该在静态资源 URL 上加版本号或 hash（如 `/dashboard?v=20260809`），但这在纯 HTML 内嵌的架构中不适用。当前最实用的做法是告知用户强制刷新的快捷键。

---

## 总结

| 类别 | 问题数 | 典型后果 | 关键教训 |
|------|--------|---------|---------|
| 缓存逻辑 | 3 | 经验无法复用 | 单元测试覆盖核心指标 |
| 文件路径 | 2 | 数据污染 | 每个请求独立工作目录 |
| API 格式变更 | 2 | 页面报错 | 变更时检查所有消费者 |
| Docker 部署 | 2 | 代码未更新 | 注意镜像缓存与容器更新的区别 |
| 前端展示 | 2 | 信息无法区分 | 紧跟数据特征设计列和截断策略 |
| 路由设计 | 2 | 功能重叠 | 定期审视路由结构 |
| 浏览器缓存 | 1 | 用户看不到更新 | 告知用户强制刷新方法 |

本项目的纠错缓存机制已经沉淀了运行时错误修复经验，这份文档则沉淀开发过程中的设计和运维经验。两者互补。
