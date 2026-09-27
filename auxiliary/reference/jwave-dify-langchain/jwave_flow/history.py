"""Run history — 每完成一次仿真任务追加一条 JSON 记录。

CLI 的「历史记录」视图只依赖这个模块，所以它必须足够宽容：
文件不存在、某一行损坏、字段缺失，都不应该抛异常。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Sequence

from .config import PROJECT_ROOT

DEFAULT_HISTORY_PATH = PROJECT_ROOT / "run" / "history.jsonl"

# 单条记录的上限，避免生成代码 / 执行日志把历史文件撑爆
MAX_CODE_CHARS = 200_000
MAX_STREAM_CHARS = 8_000
MAX_REQUIREMENT_CHARS = 8_000


def history_path(explicit: "str | Path | None" = None) -> Path:
    """历史文件位置，优先级：显式参数 > ``JWAVE_HISTORY_PATH`` > 默认。"""
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("JWAVE_HISTORY_PATH")
    if env:
        return Path(env).expanduser()
    return DEFAULT_HISTORY_PATH


def _clip(text: Any, limit: int) -> str:
    if text is None:
        return ""
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…（已截断 {len(text) - limit} 字符）"


def _title(query: str, limit: int = 48) -> str:
    first = next((line.strip() for line in (query or "").splitlines() if line.strip()), "")
    if not first:
        return "(无标题)"
    return first if len(first) <= limit else first[: limit - 1] + "…"


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def make_record(
    result: dict[str, Any],
    query: str,
    settings: Any = None,
    *,
    elapsed: float | None = None,
    backend: str = "",
) -> dict[str, Any]:
    """把 workflow 的最终 state 压缩成一条可长期保存的记录。"""
    result = result or {}
    report = result.get("param_check_report") or {}
    scalars = report.get("scalars") if isinstance(report, dict) else None

    record: dict[str, Any] = {
        "ts": time.time(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "title": _title(query),
        "query": query or "",
        "requirement": _clip(result.get("requirement"), MAX_REQUIREMENT_CHARS),
        "iterations": int(result.get("iterations") or 0),
        "success": bool(result.get("success")),
        "verified": bool(result.get("verified")),
        "elapsed": round(float(elapsed if elapsed is not None else (result.get("elapsed") or 0.0)), 3),
        "code": _clip(result.get("text") or result.get("code_final") or "", MAX_CODE_CHARS),
        "stdout": _clip(result.get("stdout"), MAX_STREAM_CHARS),
        "stderr": _clip(result.get("stderr"), MAX_STREAM_CHARS),
        "error": str(result.get("error") or ""),
        "error_hints": _as_list(result.get("error_hints")),
        "new_files": _as_list(result.get("new_files")),
        "trace": _as_list(result.get("trace")),
        "gates": {
            "param_ok": bool(result.get("param_check_ok")),
            "param_rounds": int(result.get("param_check_rounds") or 0),
            "param_issues": _as_list(result.get("param_issues")),
            "param_warnings": _as_list(result.get("param_warnings")),
            "param_constraints": _as_list(result.get("param_constraints")),
            "static_ok": not result.get("static_issues"),
            "static_rounds": int(result.get("static_rounds") or 0),
            "static_issues": _as_list(result.get("static_issues")),
            "semantic_ok": bool(result.get("verified")),
            "semantic_issues": _as_list(result.get("semantic_issues")),
            "selfcheck": result.get("selfcheck") or {},
        },
    }
    if scalars:
        record["scalars"] = scalars
    if backend:
        record["executor_backend"] = backend
    if settings is not None:
        record["model"] = {
            "analyst": getattr(settings, "analyst_model", ""),
            "coder": getattr(settings, "coder_model", ""),
            "retrieval": getattr(settings, "retrieval_backend", ""),
            "executor": getattr(settings, "executor_backend", ""),
        }
    return record


def append_record(record: dict[str, Any], path: "str | Path | None" = None) -> Path:
    """追加一条记录，返回实际写入的文件。"""
    target = history_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return target


def load_records(path: "str | Path | None" = None, limit: int | None = None) -> list[dict[str, Any]]:
    """读取历史记录，**最新的在前**。损坏的行会被静默跳过。"""
    target = history_path(path)
    if not target.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        with target.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    records.append(obj)
    except OSError:
        return []
    records.reverse()
    if limit is not None and limit >= 0:
        return records[:limit]
    return records


def clear_records(path: "str | Path | None" = None) -> bool:
    """清空历史文件（不删除文件本身，方便 IDE 里继续 tail）。"""
    target = history_path(path)
    if not target.exists():
        return False
    try:
        target.write_text("", encoding="utf-8")
    except OSError:
        return False
    return True


def status_icon(record: dict[str, Any]) -> str:
    """给历史列表用的一枚状态徽标。"""
    if record.get("verified") and record.get("success"):
        return "✅"
    if record.get("success"):
        return "⚠️"
    return "❌"


def summarize(record: dict[str, Any], width: int = 48) -> str:
    title = _title(record.get("title") or record.get("query") or "", width)
    return f"{record.get('time', '?')}  {title}"


def describe(record: dict[str, Any]) -> Sequence[tuple[str, str]]:
    """(标签, 值) 列表，供历史详情面板使用。"""
    gates = record.get("gates") or {}
    return [
        ("时间", str(record.get("time") or "?")),
        ("需求", str(record.get("title") or "?")),
        ("迭代", f"{record.get('iterations', 0)} 轮"),
        ("耗时", f"{float(record.get('elapsed') or 0):.1f}s"),
        ("运行", "成功 ✅" if record.get("success") else "失败 ❌"),
        *([("错误", str(record["error"]))] if record.get("error") else []),
        ("方案一 参数预检", "通过 ✅" if gates.get("param_ok") else f"未通过（{len(gates.get('param_issues') or [])} 项）"),
        ("方案二 静态检查", "通过 ✅" if gates.get("static_ok") else f"{len(gates.get('static_issues') or [])} 处问题"),
        ("方案三 语义门", "通过 ✅" if gates.get("semantic_ok") else f"{len(gates.get('semantic_issues') or [])} 项未通过"),
    ]
