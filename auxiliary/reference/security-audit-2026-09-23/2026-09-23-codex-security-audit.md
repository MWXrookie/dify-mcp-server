# Codex Security 只读审计报告

## 扫描信息

- 目标：`<local-workspace>`
- 审计方式：固定源码快照，只读；当前目录没有 `.git`，不做 diff 或历史审计
- 写入边界：仅写入 `work/plugin-tests/security/`
- 归档位置：`docs/security/2026-09-23-codex-security-audit.md`
- 审计重点：MCP Bearer token 流转、DeepSeek/API Key 泄露路径、executor Docker 沙箱边界、`.env`/`.gitignore`/依赖文件风险、未来 `skill_store` 的信任与质量门控边界
- 未输出任何真实密钥、token 或敏感值

## 结论摘要

共确认 2 个高严重度、3 个中严重度、2 个低严重度问题。

最高优先级问题是：未鉴权的 `/chat` 允许调用方指定任意 `base_url`，当调用方不提供自己的 API Key 时，服务端会回退使用 `DEEPSEEK_API_KEY`，并把该 Key 放入 `Authorization` 请求头发送到调用方指定的地址。这构成服务端凭据外泄路径。

其次是：`server_safe.py` 只保护 MCP `/mcp` 入口，`portal.py` 注册的 custom routes 没有同等鉴权。任何能访问绑定端口的客户端都可读取执行历史、清空历史并重跑历史代码。

## 发现

### SEC-01：任意 `base_url` 可诱导服务端泄露 DeepSeek API Key

- 严重度：高
- 置信度：高（0.97）
- 分类：SSRF 与凭据泄露
- CWE：CWE-918、CWE-522

证据位置：

- `portal.py:96`：`/chat` custom route 未要求 Bearer token。
- `portal.py:103-107`：请求体可携带调用方控制的 `model_config`。
- `portal.py:48-52`：`api_key` 优先取调用方 Key，否则回退到 `config.DEEPSEEK_API_KEY`；`base_url` 直接取调用方值。
- `portal.py:64-77`：向 `base_url + "/chat/completions"` 发起请求，并把选中的 `api_key` 写入 `Authorization: Bearer ...`。
- `compose.yaml:40-42`：网关端口绑定到内网 IP，能被该网络内客户端访问；实际绑定地址可由 `DIFY_MCP_BIND_IP` 覆盖。

误用路径：

1. 攻击者从可访问 `8001` 的网络位置发送 `POST /chat`。
2. 请求体包含非空 `requirement`、`message`，并提供 `model_config.base_url`。
3. `model_config.api_key` 留空，使服务端回退使用 `DEEPSEEK_API_KEY`。
4. `base_url` 指向攻击者控制的 HTTP/HTTPS 服务。
5. 网关把服务端 DeepSeek Key 作为 Bearer 凭据发送到该地址。

影响：

- 可窃取长期有效的 DeepSeek API Key。
- 可造成第三方 API 费用盗用和调用归因混淆。
- 请求体中的仿真需求、上下文或错误内容也会一并发给攻击者地址。

建议修复：

- 删除客户端控制的 `base_url`，或使用严格的服务端 allowlist。
- 永远不要把服务端默认 Key 与调用方提供的目标地址组合使用。
- BYOK 场景必须要求调用方同时提供自己的 Key，并改用不含服务端凭据的出站路径。
- 对 `/chat` 增加认证、授权和网络访问控制。
- 出站请求增加域名/IP allowlist，并禁止访问私网、回环、链路本地和云元数据地址。

### SEC-02：custom routes 绕过 MCP 鉴权，可读取、删除和重跑执行记录

- 严重度：高
- 置信度：高（0.98）
- 分类：缺失认证与授权
- CWE：CWE-306、CWE-862

证据位置：

- `server_safe.py:30-34`：为 FastMCP 实例配置了静态 Bearer token 校验。
- `server_safe.py:36-38`：随后注册业务工具和 portal；portal 的 `custom_route` 使用同一 HTTP 服务但没有独立鉴权检查。
- `portal.py:182-192`：`GET /dashboard/api/executions` 返回执行记录和统计。
- `portal.py:194-200`：`DELETE /dashboard/api/executions` 清空全部执行记录。
- `portal.py:202-227`：`POST /dashboard/api/rerun` 按记录 ID 取出代码并在 executor 中重跑。
- `portal.py:229-234`：`GET /dashboard/api/cache_stats` 返回纠错缓存统计和提示内容。
- `dashboard.py:107-125`：历史记录保存完整代码、stdout 和 stderr。

误用路径：

1. 客户端直接访问 `http://<gateway>:8001/dashboard/api/executions`，无需 Bearer token。
2. 读取历史中的生成代码、标准输出、错误输出和图像数据。
3. 调用 `DELETE` 清空执行历史。
4. 调用 `/dashboard/api/rerun` 触发历史代码再次执行，消耗容器资源。

影响：

- 生成代码、仿真输出和错误堆栈可能包含业务数据或内部实现细节。
- 未授权用户可以破坏审计记录。
- 重跑接口可被用于资源消耗和服务扰动。
- 当前默认绑定内网，但配置允许改成其他绑定地址；一旦端口转发到更大网络，风险会立即扩大。

建议修复：

- 在应用层用统一 middleware 保护所有非公开路由，而不是只保护 MCP transport。
- 为只读看板和管理操作设置不同权限。
- 删除或默认禁用清空、重跑等破坏性接口；如需保留，应增加认证、授权、CSRF 防护和审计日志。
- 将 Web 门户与管理 API 分离到不同监听端口或反向代理路由，并限制来源网段。

### SEC-03：Markdown 渲染未净化 HTML，且浏览器持久化保存 BYOK Key

- 严重度：中
- 置信度：高（0.94）
- 分类：跨站脚本与敏感数据存储
- CWE：CWE-79、CWE-522

证据位置：

- `dashboard.py:733-758`：`renderMarkdown` 直接把输入字符串当作 HTML 模板处理，只替换部分 Markdown 语法，不先做 HTML 转义或 allowlist 净化。
- `dashboard.py:780-783`：assistant 消息未经净化直接交给 `renderMarkdown`，结果写入 `innerHTML`。
- `dashboard.py:1312-1331` 与 `dashboard.py:1397-1401`：多轮对话页面存在相同渲染链。
- `dashboard.py:1373-1374`：模型 API Key 以明文形式写入 `localStorage`。

误用路径：

1. 攻击者诱导 Dify/LLM 报告或程序输出包含 HTML 属性事件处理器，例如带 `onerror` 的图片标签。
2. 报告进入 assistant 消息。
3. `renderMarkdown` 原样保留 HTML，并写入 `innerHTML`。
4. 浏览器执行事件处理器，读取同源 `localStorage` 中的模型 Key，或调用当前源上的未授权管理接口。

影响：

- 可窃取用户保存在浏览器中的 BYOK API Key。
- 可在同源上下文执行操作，包括读取执行历史、清空记录或触发重跑。
- 风险依赖报告内容和浏览器解析行为；源码已建立可执行路径，但没有用真实浏览器做攻击复现。

建议修复：

- 使用成熟 Markdown 渲染器并启用严格 HTML 清理，禁止事件属性和危险 URL scheme。
- 在生成 HTML 前处理完整输出，不要用自定义正则把原始字符串拼进 `innerHTML`。
- 增加 Content Security Policy，至少禁止内联脚本和未授权连接。
- 不要把长期 API Key 保存在 `localStorage`；改用服务端密钥代理、短期会话凭据或仅内存保存。

### SEC-04：未来 skill store 接受调用方自报质量证据，缺少可信来源绑定

- 严重度：中
- 置信度：高（0.92）
- 分类：数据真实性验证不足
- CWE：CWE-345、CWE-494

证据位置：

- `work/plugin-tests/superpowers/skill_store.py:19-27`：`SkillCandidate` 的 `verdict`、`metrics`、`code` 和 `evidence_reference` 都由调用方提供。
- `work/plugin-tests/superpowers/skill_store.py:62-97`：质量门只检查字段值和数值范围，不验证这些值来自哪次真实分析事件。
- `work/plugin-tests/superpowers/skill_store.py:177-259`：通过字段检查后直接持久化代码和证据引用。
- `work/plugin-tests/superpowers/skill_store.py:261-334`：检索结果会把存储的 `code` 返回给调用方。

误用路径：

1. 调用方伪造 `verdict=normal`、合理范围内的 `metrics`、非空 `evidence_reference` 和任意代码。
2. `evaluate_quality` 只验证内容形状，因此接受该候选。
3. 恶意代码和摘要进入数据库。
4. 后续检索把该代码返回给生成链或模型上下文。

影响：

- 当前原型被隔离在 `work/plugin-tests/superpowers/`，尚未接入生产 MCP，所以现状不可直接利用。
- 若按当前信任模型接入生产，会形成持久化提示注入和不安全代码复用入口，绕过“只有真实 VAL-1 通过结果才能入库”的目标。

建议修复：

- 入库接口不信任客户端传入的 `verdict` 和 `metrics`；必须由服务端分析器生成并签名。
- 把写入绑定到不可变的 `analysis_event_id`、结果哈希和验证版本，并验证证据引用确属该事件。
- 将代码视为不可信数据，不自动执行；需要执行时重新经过静态检查、沙箱和物理质量门控。
- 新技能先进入隔离候选区，人工审核或达到独立复测门槛后再提升为可用技能。
- 数据库记录来源、模型版本、验证器版本、代码哈希和审批状态，支持撤销和追踪。

### SEC-05：executor 子进程与服务同 UID、同 PID 环境，可读取服务 token 并逃逸超时清理

- 严重度：中
- 置信度：中（0.78）
- 分类：沙箱隔离不足
- CWE：CWE-250、CWE-269

证据位置：

- `executor/executor.py:17`：executor 服务从环境读取 `EXECUTOR_SHARED_TOKEN`。
- `executor/executor.py:46-68`：子进程环境被显式白名单化，这是正向控制。
- `executor/executor.py:59-67`：子进程由同一服务进程、同一 UID 启动，并创建新 session。
- `executor/executor.py:69-74`：超时只对原进程组执行 `killpg`；自行 `setsid`/分叉的子进程不在该进程组。
- `executor/Dockerfile:45` 与 `compose.yaml:9-22`：服务进程和子进程运行在同一容器、同一用户、同一 PID namespace。
- `compose.yaml:14-15`：`/tmp` 是共享且跨请求存在的 tmpfs。

误用路径：

1. 恶意生成代码读取同 UID 的 PID 1 环境，可能获得 `EXECUTOR_SHARED_TOKEN`。
2. 代码访问容器内 `127.0.0.1:8010`，调用本机 executor HTTP 接口。
3. 代码创建新 session 或后台进程，使原进程组被杀死后仍能继续运行。
4. 后台进程或 `/tmp` 文件可影响后续执行并造成资源消耗。

影响：

- 未验证到直接逃出容器或读取网关键，但突破了“每次请求独立、超时后彻底清理”的预期边界。
- 允许持久化进程或状态干扰后续仿真。
- 当前网络为 `internal: true`、根文件系统只读、capability 全部 drop、资源限制存在，限制了影响范围。
- 该结论基于 Linux 默认 `/proc` 可见性和进程语义，未在运行中的容器做攻击复现，因此置信度低于前四项。

建议修复：

- 将 broker 与不可信代码执行拆成不同 UID 或不同容器，broker token 不得对执行进程可见。
- 使用独立 PID namespace、隐藏其他进程的 procfs 或 `hidepid` 配置。
- 使用 cgroup kill 替代仅 `killpg`，并确保所有后代进程被回收。
- 每次请求使用全新工作容器或至少全新 tmpfs；禁止跨请求共享 `/tmp`。
- 执行进程不得访问 broker 管理端口；通过受限文件描述符或权限隔离的单向通道传递结果。

### SEC-06：`.dockerignore` 未排除 `.env` 及其备份变体

- 严重度：低
- 置信度：高（0.99）
- 分类：构建上下文密钥暴露
- CWE：CWE-538

证据位置：

- `.dockerignore:1-4`：只忽略缓存、日志和旧环境压缩包，没有 `.env`、`.env.*` 或 `.env.bak.*`。
- `Dockerfile:12-17`：当前使用选择性 `COPY`，所以本快照没有证据表明 `.env` 已进入镜像。

影响：

- 当前 Dockerfile 不会复制 `.env`，因此现状是防御缺口，不是已确认泄露。
- 未来改成 `COPY . .`、增加打包步骤或复用构建上下文时，真实密钥可能进入镜像层或构建缓存。

建议修复：

- 在 `.dockerignore` 增加 `.env`、`.env.*`，并显式保留 `!.env.example`。
- 增加 `*.key`、`*.pem`、凭据文件和本地数据库等规则。
- 使用 Docker BuildKit secret mount 传递运行时依赖，不把密钥放入 build context。

### SEC-07：依赖锁定不完整且安装未做哈希校验

- 严重度：低
- 置信度：中（0.76）
- 分类：软件供应链完整性不足
- CWE：CWE-494

证据位置：

- `requirements.lock.txt:1-3`：直接依赖固定版本，但扩展组件带出的传递依赖未显式锁定，也没有 hash。
- `Dockerfile:13-14`：`pip install -r` 未使用 `--require-hashes`。
- `executor/Dockerfile:26-41`：多个科学计算依赖固定版本，但 `beartype`、`wadler-lindig`、`rich` 未固定版本。

影响：

- 构建结果不能完全复现，未来镜像可能解析到不同的传递依赖。
- 没有 hash 校验时，构建无法验证下载制品与已审计制品一致。
- 这不是已确认漏洞，属于供应链加固缺口。

建议修复：

- 生成包含全部传递依赖和 SHA-256 的锁文件。
- 使用 `pip install --require-hashes` 或等价的锁文件工具。
- 在 CI 中增加依赖漏洞扫描和镜像 digest 固定。

## 已检查且未发现问题

- MCP `/mcp` 入口有静态 Bearer token 校验和 scope 要求；token 长度在启动时校验。
- executor POST 接口使用 `hmac.compare_digest` 比较共享 token。
- executor 服务位于 `internal: true` 网络，没有对外发布端口。
- executor 容器启用只读根文件系统、`no-new-privileges`、capability 全部 drop、PID/内存/CPU 限制。
- 生成代码子进程没有继承网关的 `DEEPSEEK_API_KEY`、`DIFY_API_KEY` 或 `MCP_AUTH_TOKEN`。
- SQLite 查询使用参数绑定，没有发现 SQL 注入。
- 对当前固定快照做敏感模式扫描，没有发现真实密钥、token、私钥或 `.env` 文件。

## 排除项与低置信说明

- 未把“`/health` 无需认证”列为漏洞：当前只返回服务状态和库列表，未发现敏感值。
- 未把 `DIFY_API_KEY` 固定发送到内部 nginx 列为 SSRF：目标是硬编码常量，未发现调用方控制。
- 未对依赖版本声称存在 CVE：本机没有 `pip-audit`、`safety`、`osv-scanner` 或镜像扫描器，未做在线漏洞库比对。
- 未验证 Git 历史：目标目录没有 `.git`，且用户明确要求按固定源码快照审计。
- 没有执行任何真实攻击、外连或运行时漏洞利用；所有确认项均基于当前源码数据流。
