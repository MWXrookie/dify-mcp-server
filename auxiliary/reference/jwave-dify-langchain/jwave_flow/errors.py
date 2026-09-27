"""把底层异常翻译成人能看懂的诊断。

刻意**不依赖 rich / prompt_toolkit**：交互式界面与非交互式 CLI 都从这里取文案，
这样两种入口对同一个错误的说法完全一致。
"""
from __future__ import annotations

import errno
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 仅为类型标注，避免运行期循环导入
    from .config import Settings

# 网络类问题的常见特征（httpx / httpcore / openai / socket 各自的措辞都覆盖到）
_NETWORK_MARKERS = (
    "connecterror",
    "connection error",
    "connection reset",
    "connection aborted",
    "connection refused",
    "remotedisconnected",
    "server disconnected",
    "ssl",
    "tls",
    "timed out",
    "timeout",
    "temporary failure in name resolution",
    "name or service not known",
    "nodename nor servname",
    "max retries exceeded",
)
_AUTH_MARKERS = ("authenticationerror", "invalid api key", "incorrect api key", "401", "unauthorized")
_MODEL_MARKERS = ("notfounderror", "model_not_found", "does not exist", "404")
_RATE_MARKERS = ("ratelimiterror", "rate limit", "429", "insufficient_quota", "quota")


def error_summary(exc: BaseException) -> str:
    """一行摘要：``OpenAIConnectionError: Connection error.``"""
    text = " ".join(str(exc).split())
    if not text:
        text = exc.__class__.__doc__ or "（无详细信息）"
    return f"{type(exc).__name__}: {text}"


def _blob(exc: BaseException) -> str:
    parts = [type(exc).__name__, str(exc)]
    cause = exc.__cause__ or exc.__context__
    seen = 0
    while cause is not None and seen < 4:  # 顺着异常链找根因，比如 httpcore.ConnectError
        parts.append(type(cause).__name__)
        parts.append(str(cause))
        cause = cause.__cause__ or cause.__context__
        seen += 1
    return " ".join(parts).lower()


def is_network_error(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    if getattr(exc, "errno", None) in (errno.ECONNRESET, errno.ECONNREFUSED, errno.ETIMEDOUT, errno.EHOSTUNREACH):
        return True
    blob = _blob(exc)
    return any(marker in blob for marker in _NETWORK_MARKERS)


def diagnose_error(exc: BaseException, settings: "Settings | None" = None) -> list[str]:
    """根据异常返回若干条排查建议（可能为空）。

    ``settings`` 传入时会**先**检查 Key 与 endpoint 是否属于同一服务商——
    `DEEPSEEK_API_KEY` 配 OpenAI 地址同样会表现为 `Connection reset by peer`，
    如果只看异常本身就会误判成网络问题，把人引到 MTU/代理上去。
    """
    blob = _blob(exc)
    hints: list[str] = []

    mismatch: str | None = None
    if settings is not None:
        from .config import endpoint_key_mismatch

        mismatch = endpoint_key_mismatch(settings)

    if mismatch:
        hints.append("先检查配置：API Key 与 endpoint 不属于同一服务商（这通常就是本错误的真正原因）")
        hints.append(f"· {mismatch}")

    if is_network_error(exc):
        if mismatch:
            hints.append("· 先按上一条把 endpoint 改对再重试；下面几条只在配置正确后仍失败时才需要看")
        hints.extend(
            [
                "这是网络层失败（连接被重置 / TLS 握手失败），不是生成代码的问题。",
                "· 先确认能不能直连 endpoint：curl -v $OPENAI_BASE_URL/models",
                "· 国内直连 DeepSeek 用 https://api.deepseek.com/v1；需要代理时先设好代理再启动",
                "· WSL 里常见的「Connection reset by peer」多为 MTU/代理问题：可在 Windows 侧开代理，或调小 WSL 的 MTU",
                "· httpx 会自动读取 HTTPS_PROXY / ALL_PROXY；确认它们对当前终端生效，或先 unset 掉错误的代理",
            ]
        )
    if any(marker in blob for marker in _AUTH_MARKERS):
        hints.append("API Key 无效或未授权：检查 OPENAI_API_KEY（也接受 DEEPSEEK_API_KEY）是否正确、是否过期。")
    if any(marker in blob for marker in _MODEL_MARKERS):
        hints.append("模型名或端点不存在：检查 OPENAI_BASE_URL 与 ANALYST_MODEL / CODER_MODEL 是否匹配该服务商。")
    if any(marker in blob for marker in _RATE_MARKERS):
        hints.append("触发限流/额度问题：稍后重试，或换模型/换 Key。")
    if not hints:
        hints.append("可在「运行配置」里按 t 做一次 API 连通性测试，或直接用 --check-api 定位。")
    return hints


def format_error_text(
    exc: BaseException, *, indent: str = "  ", settings: "Settings | None" = None
) -> str:
    """多行文本：摘要 + 排查建议，供终端 print 或 Rich Panel 使用。"""
    lines = [error_summary(exc), "", *diagnose_error(exc, settings)]
    return f"\n{indent}".join(lines)
