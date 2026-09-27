"""LLM plumbing: an OpenAI-compatible chat model plus small parsing helpers.

The original Dify workflow used the marketplace plugins ``deepseek-v4-pro`` /
``deepseek-coder`` together with provider-side structured output.  Here we only
assume a generic **OpenAI-compatible chat completions endpoint**, which keeps
the workflow portable across DeepSeek / vLLM / Ollama / OpenAI / ...
"""
from __future__ import annotations

import re
import time
from dataclasses import replace
from typing import Any, Sequence, Type

from pydantic import BaseModel, Field

from .config import Settings


class GeneratedCode(BaseModel):
    """Structured output of ⑤ 代码生成 (Dify schema property: ``code``)."""

    code: str = Field(default="", description="将代码注入到这里，解释器会自动运行")


class FixedCode(BaseModel):
    """Structured output of ⑦ 代码纠错 (Dify schema property: ``code_2``)."""

    code_2: str = Field(default="", description="将代码注入这里")


_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_+-]*\s*\n?|\n?```\s*$")


def strip_code_fences(text: str) -> str:
    """Remove a surrounding markdown code fence (the prompt forbids them, but
    models sometimes add them anyway)."""
    if text is None:
        return ""
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1 :]
    if t.rstrip().endswith("```"):
        t = t.rstrip()[:-3]
    return t.rstrip("\n")


def build_chat_model(settings: Settings, model: str):
    """Return a ``ChatOpenAI`` bound to the configured OpenAI-compatible API."""
    from langchain_openai import ChatOpenAI  # imported lazily: optional at import time

    if not settings.openai_api_key:
        raise RuntimeError(
            "No API key configured. Set OPENAI_API_KEY (or DEEPSEEK_API_KEY) in the "
            "environment or in a .env file next to the project root."
        )
    kwargs: dict[str, Any] = dict(
        model=model,
        api_key=settings.openai_api_key,
        temperature=settings.temperature,
        timeout=settings.request_timeout,
        max_retries=settings.max_retries,
    )
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return ChatOpenAI(**kwargs)


def message_text(message: Any) -> str:
    """把 ChatModel 的返回统一成纯文本（部分 provider 返回 content blocks）。"""
    content = getattr(message, "content", message)
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(content)


def probe_api(
    settings: Settings, *, model: str | None = None, timeout: float = 20.0
) -> tuple[bool, Any, float]:
    """发一个最小请求验证连通性：返回 ``(是否成功, 回复或异常, 耗时秒)``。

    刻意不发完整的仿真提示词——只为把「网络/鉴权/模型名」这类问题从
    「生成代码的问题」里区分出来。
    """
    model = model or settings.analyst_model
    probe_settings = replace(settings, request_timeout=timeout, max_retries=0)
    started = time.time()
    try:
        llm = build_chat_model(probe_settings, model)
        message = llm.invoke("ping")
    except Exception as exc:  # noqa: BLE001 - 调用方负责展示
        return False, exc, time.time() - started
    return True, message_text(message), time.time() - started


def _first_present(data: Any, keys: Sequence[str]) -> str | None:
    if isinstance(data, BaseModel):
        data = data.model_dump()
    if isinstance(data, dict):
        for k in keys:
            if data.get(k):
                return str(data[k])
    return None


def invoke_code_llm(
    llm,
    prompt_value,
    schema: Type[BaseModel],
    keys: Sequence[str],
) -> str:
    """Ask ``llm`` for code, preferring provider-side structured output.

    Falls back to plain text + fence stripping for endpoints that do not
    implement ``response_format`` / tool calling.
    """
    # 1) native structured output (tool calling / json_schema)
    try:
        structured = llm.with_structured_output(schema)
        result = structured.invoke(prompt_value)
        code = _first_present(result, keys)
        if code and code.strip():
            return strip_code_fences(code)
    except Exception:
        pass

    # 2) plain completion
    message = llm.invoke(prompt_value)
    text = message.content if hasattr(message, "content") else str(message)
    if isinstance(text, list):  # some providers return content blocks
        text = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in text
        )
    return strip_code_fences(text)
