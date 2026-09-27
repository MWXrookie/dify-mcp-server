"""旁分支的「只掩盖未修复」：把 DeepSeek key 配 OpenAI 地址误报成网络问题。

原实现（6f21b88）只加了错误归因与 `--check-api`，但：
  * config.py 仍不管 base_url —— 根因没修
    只设 DEEPSEEK_API_KEY 时 base_url=None，于是拿 DeepSeek 的 key 去连
    api.openai.com，报 `Connection reset by peer`
  * errors.py 把该错误一律归因成「网络 / WSL MTU / 代理」，把人带偏
  * --check-api 探测的也是那个错误地址

本文件锁定：根因修复 + 归因能指出配置不匹配。
"""
from __future__ import annotations

import pytest

from jwave_flow.cli import main
from jwave_flow.config import (
    DEEPSEEK_DEFAULT_BASE_URL,
    Settings,
    endpoint_key_mismatch,
    endpoint_provider,
)
from jwave_flow.errors import diagnose_error, format_error_text

_ENV = ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_BASE_URL", "DEEPSEEK_BASE_URL")


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VERBOSE", "0")


# --------------------------- provider 判定 --------------------------- #
@pytest.mark.parametrize(
    "url,expected",
    [
        (None, "openai"),
        ("https://api.deepseek.com/v1", "deepseek"),
        ("https://api.openai.com/v1", "openai"),
        ("http://localhost:8000/v1", "local"),
        ("http://127.0.0.1:11434/v1", "local"),
        ("https://my-gateway.internal/v1", "other"),
    ],
)
def test_endpoint_provider(url, expected):
    assert endpoint_provider(url) == expected


# --------------------------- 不匹配判定 --------------------------- #
def test_deepseek_key_with_openai_url_is_a_mismatch(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    msg = endpoint_key_mismatch(Settings.from_env())
    assert msg and "DEEPSEEK_API_KEY" in msg and "api.deepseek.com" in msg


def test_deepseek_key_with_deepseek_url_is_fine(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    settings = Settings.from_env()
    assert settings.openai_base_url == DEEPSEEK_DEFAULT_BASE_URL   # 自动推断
    assert endpoint_key_mismatch(settings) is None


def test_deepseek_key_with_self_hosted_gateway_is_fine(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
    assert endpoint_key_mismatch(Settings.from_env()) is None


def test_openai_key_with_openai_url_is_fine(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-oa")
    assert endpoint_key_mismatch(Settings.from_env()) is None


# --------------------------- 归因 --------------------------- #
def _conn_error():
    err = RuntimeError("Connection error.")
    err.__cause__ = OSError("Connection reset by peer")
    return err


def test_diagnosis_flags_config_before_network(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    hints = diagnose_error(_conn_error(), Settings.from_env())
    assert "Key 与 endpoint 不属于同一服务商" in hints[0]
    assert "DEEPSEEK_API_KEY" in hints[1]


def test_diagnosis_without_settings_keeps_legacy_network_hints():
    hints = diagnose_error(_conn_error())
    assert any("网络层失败" in h for h in hints)
    assert not any("不属于同一服务商" in h for h in hints)


def test_format_error_text_includes_mismatch(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    text = format_error_text(_conn_error(), settings=Settings.from_env())
    assert "api.deepseek.com" in text


# --------------------------- --check-api（不联网） --------------------------- #
def test_check_api_stops_on_mismatch_before_probing(monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    rc = main(["--check-api"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "配置不匹配" in err          # 而不是「连通性测试失败」
    assert "provider=openai" in err


def test_check_api_without_key(monkeypatch, capsys):
    rc = main(["--check-api"])
    assert rc == 2
    assert "未配置 API Key" in capsys.readouterr().err
