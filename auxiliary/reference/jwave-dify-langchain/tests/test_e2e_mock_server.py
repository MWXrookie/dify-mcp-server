"""End-to-end test through the *real* LangChain OpenAI client.

A tiny mock OpenAI-compatible server stands in for the LLM, so the whole stack
is exercised for real: HTTP -> ChatOpenAI -> prompts -> graph -> executor,
including the "generate -> run -> fails -> repair -> run -> passes" loop.

Skipped automatically where binding a localhost socket is not permitted.
"""
from __future__ import annotations

import json
import socket
import threading

import pytest

from jwave_flow.cli import main

REQUIREMENT = "需求描述：二维时域声学仿真，1500 m/s，5 MHz 点源。"
PARAMS = '{"sound_speed": 1500.0, "source_frequency": 5e6}'
BUGGY = "import sys\nprint('run 1')\nsys.stderr.write('NameError: name jnp is not defined\\n')\n"
FIXED = (
    "import json\n"
    "import jax.numpy as jnp\n"
    "print('run 2 ok', jnp.zeros(2).sum())\n"
    "print(\"__JWAVE_SELFCHECK__\" + json.dumps("
    "{'finite': True, 'abs_max': 5016.6, 'shape': [1001, 64, 64, 1], 'f0': 5e6}))\n"
)


def _reply_for(messages) -> str:
    blob = json.dumps(messages, ensure_ascii=False)
    if "需求分析师" in blob:
        return REQUIREMENT
    if "参数提取器" in blob:
        return PARAMS
    if "代码生成器" in blob:
        return BUGGY
    if "代码改正器" in blob:
        return FIXED
    return "?"


def _make_handler():
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silence
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            payload = json.dumps(
                {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": body.get("model", "mock"),
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": _reply_for(body.get("messages", [])),
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return Handler


@pytest.fixture(scope="module")
def mock_openai():
    from http.server import HTTPServer

    try:
        server = HTTPServer(("127.0.0.1", 0), _make_handler())
    except (OSError, PermissionError) as exc:  # sandbox without sockets
        pytest.skip(f"cannot bind a local socket: {exc}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.shutdown()


def test_full_workflow_against_mock_llm(mock_openai, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    monkeypatch.setenv("OPENAI_BASE_URL", mock_openai)
    monkeypatch.setenv("ANALYST_MODEL", "mock-analyst")
    monkeypatch.setenv("CODER_MODEL", "mock-coder")
    monkeypatch.setenv("EXECUTOR_BACKEND", "subprocess")
    monkeypatch.setenv("WORKDIR", str(tmp_path / "run"))

    rc = main(["做个二维时域声学仿真", "--json"])
    out = json.loads(capsys.readouterr().out)  # --json prints pure JSON on stdout

    assert rc == 0
    assert out["success"] is True
    assert out["verified"] is True
    assert out["iterations"] == 2                    # first run fails, repair, second passes
    assert out["text"] == FIXED.rstrip("\n")
    assert out["requirement"] == REQUIREMENT
    assert out["stdout"].startswith("run 2 ok")
    # 三道新关卡都真的跑过了（方案一/二/三）
    trace = "\n".join(out["trace"])
    for marker in ["④b 参数预检 通过", "⑤b 静态检查", "⑥b 语义门 通过", "⑦ 代码纠错", "⑧ 输出"]:
        assert marker in trace
    assert out["selfcheck"]["abs_max"] == 5016.6
