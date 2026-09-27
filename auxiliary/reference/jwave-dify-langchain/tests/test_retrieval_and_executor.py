"""Knowledge retrieval + code executor contracts."""
from __future__ import annotations

from pathlib import Path

from jwave_flow.config import Settings
from jwave_flow.executor import SubprocessExecutor, get_executor
from jwave_flow.knowledge import build_retriever, load_knowledge_base, render_template_transform

ROOT = Path(__file__).resolve().parent.parent


def _settings(**kw):
    return Settings.from_env(kb_path=ROOT / "kb" / "jwave_kb_organized.md", **kw)


def test_kb_loads_and_chunks():
    docs = load_knowledge_base(ROOT / "kb" / "jwave_kb_organized.md")
    assert len(docs) > 20
    assert any("Medium" in d.page_content for d in docs)


def test_bm25_retrieval_is_relevant():
    retriever = build_retriever(_settings(top_k=4))
    hits = retriever.invoke("频域 helmholtz 求解器 边界条件")
    joined = "\n".join(h.page_content for h in hits)
    assert "helmholtz" in joined.lower() or "pml" in joined.lower()


def test_template_transform_matches_dify():
    retriever = build_retriever(_settings(top_k=3))
    docs = retriever.invoke("声速")
    rendered = render_template_transform(docs)
    # Dify: {% for item in arg1 %}{{ item.content }}\r\n{% endfor %}
    assert rendered == "".join(f"{d.page_content}\n" for d in docs)


def test_subprocess_executor_contract():
    ex = SubprocessExecutor(workdir="/tmp/jwave-test-exec", timeout=30)
    r = ex.run("print('hello'); import sys; print('oops', file=sys.stderr)")
    assert r.stdout.strip() == "hello"
    assert r.stderr.strip() == "oops"
    assert not r.ok
    r2 = ex.run("print('fine')")
    assert r2.ok and r2.stdout.strip() == "fine"


def test_executor_factory():
    assert isinstance(get_executor(_settings(executor_backend="subprocess")), SubprocessExecutor)


def test_default_exec_env_keeps_stderr_clean():
    """The loop treats any stderr as failure, so the defaults must avoid noise."""
    env = Settings.from_env().exec_env
    assert env["JAX_PLATFORMS"] == "cpu"        # CUDA segfaults on this host
    assert env["MPLBACKEND"] == "Agg"
    assert env["MPLCONFIGDIR"]                  # matplotlib cache warning -> stderr
