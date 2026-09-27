"""Environment-driven configuration (kept deliberately portable).

Everything that differs between machines lives here and is read from
environment variables / a local ``.env`` file, so the workflow can be moved to
another host without editing code.
"""
from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

try:  # optional dependency
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*_args, **_kwargs):  # type: ignore
        return False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KB = PROJECT_ROOT / "kb" / "jwave_kb_organized.md"
DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def resolve_llm_endpoint() -> tuple[str | None, str | None]:
    """Return ``(api_key, base_url)`` keeping the **pair** consistent.

    Regression guard: previously only ``DEEPSEEK_API_KEY`` was honoured as a
    key *fallback*, while ``base_url`` stayed ``None`` -> the request went to
    ``api.openai.com`` carrying a DeepSeek key and died with
    ``Connection reset by peer``.  The endpoint now follows whichever key was
    actually picked.
    """
    openai_key = _env("OPENAI_API_KEY")
    deepseek_key = _env("DEEPSEEK_API_KEY")
    explicit_base = _env("OPENAI_BASE_URL") or _env("DEEPSEEK_BASE_URL")

    key = openai_key or deepseek_key
    base = explicit_base
    if base is None and key is not None:
        # 用的是 DeepSeek 的 key（没设 OPENAI_API_KEY，或两者其实是同一个 key）
        if openai_key is None or key == deepseek_key:
            base = DEEPSEEK_DEFAULT_BASE_URL
    return key, base


# --------------------------------------------------------------------------- #
# endpoint / key 一致性判断（供错误归因使用）
# --------------------------------------------------------------------------- #
def key_source() -> str | None:
    """实际生效的 API Key 来自哪个环境变量。"""
    if _env("OPENAI_API_KEY"):
        return "OPENAI_API_KEY"
    if _env("DEEPSEEK_API_KEY"):
        return "DEEPSEEK_API_KEY"
    return None


def endpoint_provider(base_url: str | None) -> str:
    """粗略判断 endpoint 属于哪家服务商。"""
    if not base_url:
        return "openai"                      # langchain/openai 自己的默认地址
    url = base_url.lower()
    if "deepseek" in url:
        return "deepseek"
    if "openai.com" in url:
        return "openai"
    if "dashscope" in url or "aliyun" in url:
        return "dashscope"
    if "localhost" in url or "127.0.0.1" in url or "0.0.0.0" in url:
        return "local"
    return "other"


def endpoint_key_mismatch(settings: "Settings | None") -> str | None:
    """Key 与 endpoint 明显不属于同一服务商时给出说明，否则 ``None``。

    典型的坑：`DEEPSEEK_API_KEY` 配上了 `OPENAI_BASE_URL=https://api.openai.com/v1`
    （或没设 base_url 而落到 OpenAI 默认地址）。此时报错信息看起来像网络问题
    （`Connection reset by peer`），实际是配置串了——必须指出来，否则用户会
    一直去调 MTU / 代理。
    """
    if settings is None or key_source() != "DEEPSEEK_API_KEY":
        return None
    provider = endpoint_provider(settings.openai_base_url)
    if provider in ("deepseek", "local", "other"):
        return None                           # 自建网关/中转都算合理
    endpoint = settings.openai_base_url or "https://api.openai.com/v1（默认）"
    return (
        f"API Key 来自 DEEPSEEK_API_KEY，但 endpoint 指向 {endpoint}"
        f"（provider={provider}）。请设置 OPENAI_BASE_URL={DEEPSEEK_DEFAULT_BASE_URL}"
        "（只设 DEEPSEEK_API_KEY、不设 OPENAI_BASE_URL 时会自动推断）"
    )


@dataclass
class Settings:
    """All runtime knobs for the workflow."""

    # --- LLM (anything that speaks the OpenAI chat-completions API) ---
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    analyst_model: str = "deepseek-flash"
    coder_model: str = "deepseek-flash"
    temperature: float = 0.7
    request_timeout: float = 120.0
    max_retries: int = 2

    # --- Knowledge retrieval -------------------------------------------
    # "bm25"   -> pure-python lexical retrieval, no network, no extra deps
    # "openai" -> OpenAI-compatible embeddings + in-memory vector store
    kb_path: Path = field(default_factory=lambda: DEFAULT_KB)
    retrieval_backend: str = "bm25"
    top_k: int = 4
    embedding_model: str = "text-embedding-3-small"

    # --- Code execution ------------------------------------------------
    # "subprocess" (default) | "jupyter" | "mcp" | "auto"
    executor_backend: str = "subprocess"
    exec_python: str = sys.executable
    exec_timeout: float = 600.0
    # Defaults that keep generated simulation code *quiet on stderr*, because the
    # ⑦ 条件分支 node treats any stderr output as a failure:
    #   * JAX_PLATFORMS=cpu  -> the default CUDA backend segfaults on some hosts
    #   * MPLBACKEND=Agg     -> no GUI window when running headless
    #   * MPLCONFIGDIR       -> otherwise matplotlib prints a cache warning to stderr
    exec_env: dict[str, str] = field(
        default_factory=lambda: {
            "JAX_PLATFORMS": "cpu",
            "MPLBACKEND": "Agg",
            "MPLCONFIGDIR": os.path.join(tempfile.gettempdir(), "jwave-flow-mpl"),
        }
    )
    workdir: Path = field(default_factory=lambda: PROJECT_ROOT / "run")

    # --- 方案一：参数物理预检 (pre-codegen physical check) ---------------
    param_check_enabled: bool = True
    # 每波长最少网格点数（经验：PSTD 一般 ≥6，保守可取 8~10）
    min_points_per_wavelength: float = 6.0
    # 参数不合格时回退「参数提取」的最大重试轮数
    param_check_max_rounds: int = 2
    # 估算时间步 (jwave TimeAxis.from_medium 的默认 CFL)
    default_cfl: float = 0.3

    # --- 方案二：AST 静态规则检查 ----------------------------------------
    static_check_enabled: bool = True

    # --- 方案三：输出契约 + 数值门 ---------------------------------------
    semantic_check_enabled: bool = True
    # 是否强制要求生成代码打印 __JWAVE_SELFCHECK__ 自检行
    require_selfcheck: bool = True
    # |p|max 必须 > min_abs_max（否则视为激励没起作用）
    min_abs_max: float = 0.0
    # |p|max 必须 <= max_abs_max（否则视为数值发散）
    max_abs_max: float = 1e12

    # --- Workflow -------------------------------------------------------
    max_iterations: int = 10          # mirrors Dify loop_count
    verbose: bool = True

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env")
        load_dotenv()  # also honour a .env in the current directory
        api_key, base_url = resolve_llm_endpoint()
        kwargs: dict = dict(
            openai_api_key=api_key,
            openai_base_url=base_url,
            analyst_model=_env("ANALYST_MODEL", "deepseek-flash"),
            coder_model=_env("CODER_MODEL", "deepseek-flash"),
            temperature=float(_env("LLM_TEMPERATURE", "0.7")),
            request_timeout=float(_env("LLM_TIMEOUT", "120")),
            kb_path=Path(_env("KB_PATH", str(DEFAULT_KB))).expanduser(),
            retrieval_backend=_env("RETRIEVAL_BACKEND", "bm25"),
            top_k=int(_env("RETRIEVAL_TOP_K", "4")),
            embedding_model=_env("EMBEDDING_MODEL", "text-embedding-3-small"),
            executor_backend=_env("EXECUTOR_BACKEND", "subprocess"),
            exec_python=_env("EXEC_PYTHON", sys.executable),
            exec_timeout=float(_env("EXEC_TIMEOUT", "600")),
            workdir=Path(_env("WORKDIR", str(PROJECT_ROOT / "run"))).expanduser(),
            param_check_enabled=(_env("PARAM_CHECK", "1") not in ("0", "false", "False")),
            static_check_enabled=(_env("STATIC_CHECK", "1") not in ("0", "false", "False")),
            semantic_check_enabled=(_env("SEMANTIC_CHECK", "1") not in ("0", "false", "False")),
            require_selfcheck=(_env("REQUIRE_SELFCHECK", "1") not in ("0", "false", "False")),
            min_abs_max=float(_env("MIN_ABS_MAX", "0")),
            max_abs_max=float(_env("MAX_ABS_MAX", "1e12")),
            min_points_per_wavelength=float(_env("MIN_POINTS_PER_WAVELENGTH", "6")),
            param_check_max_rounds=int(_env("PARAM_CHECK_MAX_ROUNDS", "2")),
            default_cfl=float(_env("DEFAULT_CFL", "0.3")),
            max_iterations=int(_env("LOOP_MAX_ITERATIONS", "10")),
            verbose=(_env("VERBOSE", "1") not in ("0", "false", "False")),
        )
        kwargs.update(overrides)
        return cls(**kwargs)

    def resolved_kb_path(self) -> Path:
        return self.kb_path if self.kb_path.is_absolute() else (PROJECT_ROOT / self.kb_path)
