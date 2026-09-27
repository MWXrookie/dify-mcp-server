"""回归：LLM 的 key 与 base_url 必须成对解析。

历史 bug：只设 ``DEEPSEEK_API_KEY`` 时，key 会回退到 DeepSeek，但 ``base_url``
仍是 ``None`` → 请求发往 ``api.openai.com`` 并带着 DeepSeek 的 key，
最终 `Connection reset by peer` / `OpenAIConnectionError`。

    $ python -m jwave_flow "..."
    模型: ... base_url=(openai default)          <-- 症状
    openai.APIConnectionError: Connection error.
"""
from __future__ import annotations

import pytest

from jwave_flow.config import DEEPSEEK_DEFAULT_BASE_URL, Settings, resolve_llm_endpoint

_ENV_VARS = ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_BASE_URL", "DEEPSEEK_BASE_URL")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_only_deepseek_key_implies_deepseek_base_url(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    key, base = resolve_llm_endpoint()
    assert key == "sk-ds-test"
    assert base == DEEPSEEK_DEFAULT_BASE_URL
    assert Settings.from_env().openai_base_url == DEEPSEEK_DEFAULT_BASE_URL


def test_only_openai_key_keeps_the_openai_default(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oa-test")
    key, base = resolve_llm_endpoint()
    assert key == "sk-oa-test"
    assert base is None            # -> langchain/openai 自己的默认地址
    assert Settings.from_env().openai_base_url is None


def test_explicit_base_url_always_wins(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://my.gateway/v1")
    assert resolve_llm_endpoint()[1] == "http://my.gateway/v1"

    monkeypatch.delenv("OPENAI_BASE_URL")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "http://ds.gateway/v1")
    assert resolve_llm_endpoint()[1] == "http://ds.gateway/v1"


def test_same_key_for_both_still_goes_to_deepseek(monkeypatch):
    # 有些人把 DeepSeek 的 key 同时 export 成 OPENAI_API_KEY
    monkeypatch.setenv("OPENAI_API_KEY", "sk-shared")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-shared")
    assert resolve_llm_endpoint()[1] == DEEPSEEK_DEFAULT_BASE_URL


def test_no_key_at_all_resolves_to_nothing(monkeypatch):
    assert resolve_llm_endpoint() == (None, None)
