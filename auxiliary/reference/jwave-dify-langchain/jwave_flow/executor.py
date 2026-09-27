"""Code execution backends — the replacement for the (broken) MCP tool.

The original Dify graph called the ``RUN_PYTHON_CODE`` MCP tool of
``python-mcp-server`` (a *persistent Jupyter kernel*) and consumed a dict with
``stdout / stderr / results / outputs / new_files / execution_time``.

That exact contract is reproduced here by three interchangeable backends:

======  =========================================================  =============
name    mechanism                                                  needs
======  =========================================================  =============
subproc one-shot ``python <tmpfile>`` subprocess (default)          nothing
jupyter persistent kernel through ``jupyter_client``                ``ipykernel``
mcp     spawns ``python-mcp-server`` and calls ``run_python_code``  ``mcp``
======  =========================================================  =============

``auto`` tries ``jupyter`` first and silently degrades to ``subprocess``.

.. warning:: Generated code is executed with the privileges of the current
   user.  Timeouts and a scratch working directory are applied, but this is
   *not* a security sandbox — do not feed the workflow untrusted prompts.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings

_ANSI_CSI = re.compile(r"\x1b\[[0-9;]*[mK]")
_ANSI_OTHER = re.compile(r"\x1b[\[\]\(\)][0-9;]*[A-Za-z]")


def strip_ansi(text: str | None) -> str:
    """Remove ANSI escapes — Dify's ``代码执行 2`` node did exactly this."""
    if not text:
        return ""
    return _ANSI_OTHER.sub("", _ANSI_CSI.sub("", text))


@dataclass
class ExecutionResult:
    """Mirrors the payload of Dify's ``代码执行 2`` code node."""

    stdout: str = ""
    stderr: str = ""
    results: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    new_files: list[str] = field(default_factory=list)
    execution_time: float = 0.0
    backend: str = ""

    @property
    def ok(self) -> bool:
        """Dify's loop condition: ``stderr`` is empty."""
        return self.stderr.strip() == ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "results": self.results,
            "outputs": self.outputs,
            "new_files": self.new_files,
            "execution_time": round(self.execution_time, 3),
            "backend": self.backend,
        }


def _snapshot(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


class BaseExecutor(ABC):
    name = "base"

    @abstractmethod
    def run(self, code: str) -> ExecutionResult: ...

    def close(self) -> None:  # pragma: no cover - default no-op
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


# --------------------------------------------------------------------------- #
# 1. subprocess (default, most portable)
# --------------------------------------------------------------------------- #
class SubprocessExecutor(BaseExecutor):
    name = "subprocess"

    def __init__(
        self,
        python: str | None = None,
        workdir: Path | str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ):
        self.python = python or sys.executable
        self.workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="jwave-run-"))
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.env = dict(os.environ)
        if env:
            self.env.update(env)

    def run(self, code: str) -> ExecutionResult:
        before = _snapshot(self.workdir)
        script = self.workdir / "_generated.py"
        script.write_text(code, encoding="utf-8")

        start = time.time()
        try:
            proc = subprocess.run(
                [self.python, str(script)],
                cwd=str(self.workdir),
                env=self.env,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            stdout, stderr = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = f"TimeoutError: execution exceeded {self.timeout}s"
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", "replace")
            stderr = f"{stderr}\n{getattr(exc, 'stderr', '') or ''}".strip()
        elapsed = time.time() - start

        after = _snapshot(self.workdir)
        new_files = sorted(after - before - {"_generated.py"})
        return ExecutionResult(
            stdout=strip_ansi(stdout),
            stderr=strip_ansi(stderr).strip(),
            new_files=new_files,
            execution_time=elapsed,
            backend=self.name,
        )


# --------------------------------------------------------------------------- #
# 2. persistent Jupyter kernel (stateful, what python-mcp-server uses)
# --------------------------------------------------------------------------- #
class JupyterExecutor(BaseExecutor):
    name = "jupyter"

    def __init__(
        self,
        python: str | None = None,
        workdir: Path | str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ):
        self.python = python or sys.executable
        self.workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="jwave-kernel-"))
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout or 600.0
        self.env = dict(os.environ)
        if env:
            self.env.update(env)
        self._km = None
        self._kc = None

    def _ensure_kernel(self):
        if self._kc is not None:
            return
        from jupyter_client.manager import KernelManager

        km = KernelManager(kernel_cmd=[self.python, "-m", "ipykernel", "-f", "{connection_file}"])
        km.start_kernel(env=self.env, cwd=str(self.workdir))
        kc = km.client()
        kc.start_channels()
        kc.wait_for_ready(timeout=120)
        self._km, self._kc = km, kc

    def run(self, code: str) -> ExecutionResult:
        import queue

        self._ensure_kernel()
        before = _snapshot(self.workdir)

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        results: list[str] = []
        outputs: list[str] = []

        start = time.time()
        msg_id = self._kc.execute(code)
        while True:
            try:
                msg = self._kc.get_iopub_msg(timeout=self.timeout)
            except queue.Empty:
                stderr_parts.append(f"TimeoutError: no kernel output within {self.timeout}s")
                break
            if msg.get("parent_header", {}).get("msg_id") != msg_id:
                continue
            kind, content = msg["msg_type"], msg["content"]
            if kind == "stream":
                (stderr_parts if content.get("name") == "stderr" else stdout_parts).append(
                    content.get("text", "")
                )
            elif kind == "error":
                stderr_parts.append("\n".join(content.get("traceback", [])))
            elif kind == "execute_result":
                data = content.get("data", {})
                if "text/plain" in data:
                    results.append(data["text/plain"])
                self._save_rich(data, outputs)
            elif kind == "display_data":
                self._save_rich(content.get("data", {}), outputs)
            elif kind == "status" and content.get("execution_state") == "idle":
                break
        elapsed = time.time() - start

        after = _snapshot(self.workdir)
        return ExecutionResult(
            stdout=strip_ansi("".join(stdout_parts)),
            stderr=strip_ansi("\n".join(p for p in stderr_parts if p)).strip(),
            results=results,
            outputs=outputs,
            new_files=sorted(after - before),
            execution_time=elapsed,
            backend=self.name,
        )

    def _save_rich(self, data: dict, outputs: list[str]) -> None:
        outdir = self.workdir / "outputs"
        for mime, payload in data.items():
            ext = {
                "image/png": ".png",
                "image/jpeg": ".jpg",
                "image/svg+xml": ".svg",
                "application/json": ".json",
            }.get(mime)
            if not ext:
                continue
            outdir.mkdir(parents=True, exist_ok=True)
            name = f"output_{int(time.time()*1000)}_{len(outputs)}{ext}"
            path = outdir / name
            if mime.startswith("image/"):
                import base64

                path.write_bytes(base64.b64decode(payload))
            else:
                path.write_text(str(payload), encoding="utf-8")
            outputs.append(str(path.relative_to(self.workdir)))

    def close(self) -> None:
        if self._kc is not None:
            try:
                self._kc.stop_channels()
            except Exception:
                pass
        if self._km is not None:
            try:
                self._km.shutdown_kernel(now=True)
            except Exception:
                pass
        self._km = self._kc = None


# --------------------------------------------------------------------------- #
# 3. python-mcp-server over stdio (the closest match to the Dify setup)
# --------------------------------------------------------------------------- #
class McpExecutor(BaseExecutor):
    name = "mcp"

    def __init__(
        self,
        python: str | None = None,
        workdir: Path | str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        command: list[str] | None = None,
    ):
        self.python = python or sys.executable
        self.workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="jwave-mcp-"))
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout or 600.0
        self.env = dict(os.environ)
        if env:
            self.env.update(env)
        # invoke through the interpreter so it works without a PATH entry
        self.command = command or [
            self.python, "-m", "python_mcp_server.server", "--transport", "stdio"
        ]
        self._loop = None
        self._thread = None
        self._session = None
        self._stop_event = None

    def _start(self):
        if self._session is not None:
            return
        import asyncio
        import threading

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        ready = threading.Event()
        error: list[BaseException] = []

        async def _serve():
            params = StdioServerParameters(
                command=self.command[0],
                args=list(self.command[1:]) + ["--workspace", str(self.workdir), "--python", self.python],
                env=self.env,
                cwd=str(self.workdir),  # keep the server's workspace/ inside our workdir
            )
            try:
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        self._session = session
                        self._stop_event = asyncio.Event()
                        ready.set()
                        await self._stop_event.wait()  # keep the session alive
            except BaseException as exc:  # pragma: no cover
                error.append(exc)
                ready.set()

        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(_serve())
            except Exception:
                pass
            finally:
                try:
                    self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                except Exception:
                    pass
                self._loop.close()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        ready.wait(timeout=120)
        if self._session is None:
            raise RuntimeError(f"could not start python-mcp-server: {error}")

    def run(self, code: str) -> ExecutionResult:
        import asyncio

        self._start()
        start = time.time()
        fut = asyncio.run_coroutine_threadsafe(
            self._session.call_tool("run_python_code", {"code": code}), self._loop
        )
        try:
            result = fut.result(timeout=self.timeout)
        except Exception as exc:
            return ExecutionResult(
                stderr=f"{type(exc).__name__}: {exc}", execution_time=time.time() - start, backend=self.name
            )

        payload = _mcp_result_to_dict(result)
        return ExecutionResult(
            stdout=strip_ansi(payload.get("stdout", "")),
            stderr=strip_ansi(payload.get("stderr", "")).strip(),
            results=list(payload.get("results", []) or []),
            outputs=list(payload.get("outputs", []) or []),
            new_files=list(payload.get("new_files", []) or []),
            execution_time=float(payload.get("execution_time", time.time() - start)),
            backend=self.name,
        )

    def close(self) -> None:
        if self._loop is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=15)
        self._loop = self._thread = self._session = None


def _mcp_result_to_dict(result) -> dict:
    """Normalise an MCP ``CallToolResult`` into the Dify-style dict."""
    import json

    if getattr(result, "structuredContent", None):
        content = result.structuredContent
        if isinstance(content, dict) and "result" in content and len(content) == 1:
            content = content["result"]
        if isinstance(content, dict):
            return content

    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
        if isinstance(data, dict):
            return data
    return {}


# --------------------------------------------------------------------------- #
# factory
# --------------------------------------------------------------------------- #
def get_executor(settings: Settings) -> BaseExecutor:
    backend = (settings.executor_backend or "subprocess").lower()
    workdir = Path(settings.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    # make sure MPLCONFIGDIR (if configured) exists, else matplotlib warns on stderr
    mpl_dir = settings.exec_env.get("MPLCONFIGDIR")
    if mpl_dir:
        Path(mpl_dir).mkdir(parents=True, exist_ok=True)

    common = dict(
        python=settings.exec_python,
        workdir=workdir,
        timeout=settings.exec_timeout,
        env=settings.exec_env,
    )
    if backend == "subprocess":
        return SubprocessExecutor(**common)
    if backend == "jupyter":
        return JupyterExecutor(**common)
    if backend == "mcp":
        return McpExecutor(**common)
    if backend == "auto":
        try:
            executor = JupyterExecutor(**common)
            executor._ensure_kernel()
            return executor
        except Exception:
            return SubprocessExecutor(**common)
    raise ValueError(f"unknown executor backend: {settings.executor_backend!r}")
