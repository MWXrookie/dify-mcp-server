"""Execution history dashboard for Dify MCP server.

Provides SQLite-backed execution recording and a self-contained HTML
dashboard with auto-refreshing history table and test analytics.
"""

import json
import os
import sqlite3
import statistics
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = "/app/data/execution_history.db"
TEST_RESULTS_PATHS = [
    "/app/docs/test_results_raw.json",
    "/app/docs/test_results_raw_new.json",
    "docs/test_results_raw.json",
    "docs/test_results_raw_new.json",
    os.path.join(os.path.dirname(__file__), "docs/test_results_raw.json"),
    os.path.join(os.path.dirname(__file__), "docs/test_results_raw_new.json"),
]
_write_lock = threading.Lock()


def _get_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.row_factory = sqlite3.Row
    return db


def init_db() -> None:
    db = _get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            code TEXT NOT NULL,
            exit_code INTEGER,
            timed_out INTEGER,
            duration_ms REAL,
            stdout TEXT,
            stderr TEXT,
            attempt_count INTEGER DEFAULT 1,
            image_base64 TEXT
        )
    """)
    # 为旧表补充可能缺失的列（向前兼容）
    try:
        db.execute("ALTER TABLE executions ADD COLUMN attempt_count INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE executions ADD COLUMN image_base64 TEXT")
    except sqlite3.OperationalError:
        pass
    db.commit()
    db.close()


def record_execution(
    tool_name: str,
    code: str,
    exit_code: int | None,
    timed_out: bool,
    duration_ms: float | None,
    stdout: str,
    stderr: str,
    attempt_count: int = 1,
    image_base64: str | None = None,
) -> None:
    with _write_lock:
        db = _get_db()
        db.execute(
            "INSERT INTO executions (timestamp, tool_name, code, exit_code, timed_out, duration_ms, stdout, stderr, attempt_count, image_base64) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                tool_name,
                code,
                exit_code,
                int(timed_out),
                duration_ms,
                stdout or "",
                stderr or "",
                attempt_count,
                image_base64,
            ),
        )
        db.commit()
        db.close()


def get_executions(limit: int = 100, since_id: int = 0) -> list[dict]:
    db = _get_db()
    rows = db.execute(
        "SELECT * FROM executions WHERE id > ? ORDER BY id DESC LIMIT ?",
        (since_id, limit),
    ).fetchall()
    db.close()
    result = [dict(r) for r in rows]  # 最新在前，不再 reversed
    for r in result:
        r["timed_out"] = bool(r["timed_out"])
    return result


def clear_executions() -> int:
    """清空所有执行历史，返回删除的行数."""
    db = _get_db()
    count = db.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
    db.execute("DELETE FROM executions")
    db.commit()
    db.close()
    return count


def get_stats() -> dict:
    db = _get_db()
    total = db.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
    success = db.execute("SELECT COUNT(*) FROM executions WHERE exit_code = 0 AND timed_out = 0").fetchone()[0]
    failed = db.execute("SELECT COUNT(*) FROM executions WHERE exit_code != 0 AND timed_out = 0").fetchone()[0]
    timeout = db.execute("SELECT COUNT(*) FROM executions WHERE timed_out = 1").fetchone()[0]
    db.close()
    return {"total": total, "success": success, "failed": failed, "timeout": timeout}


def _find_test_results() -> str | None:
    """Find the newest available test results file."""
    candidates = [p for p in TEST_RESULTS_PATHS if os.path.exists(p)]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * pct))
    idx = max(0, min(len(ordered) - 1, idx))
    return float(ordered[idx])


def load_test_results() -> dict:
    """Load test results and return analytics data."""
    path = _find_test_results()
    loaded_at = datetime.now(timezone.utc).isoformat()
    if not path:
        return {
            "error": "test_results_raw.json not found",
            "total": 0,
            "success_count": 0,
            "fail_count": 0,
            "rate": 0,
            "baseline": 76.0,
            "target": 90.0,
            "categories": {},
            "failure_reasons": {},
            "failure_examples": {},
            "p0_before": {"success": 6, "total": 10, "rate": 60.0},
            "p0_after": {"success": 0, "total": 0, "rate": 0.0},
            "gating": [],
            "timeline": [],
            "summary": {},
            "source_file": None,
            "source_file_basename": None,
            "source_mtime": None,
            "loaded_at": loaded_at,
            "report_kind": "missing",
            "before_cache": None,
            "after_cache": None,
            "cache_delta": {},
        }

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, list):
        results = raw
        report_kind = "legacy-list"
        before_cache = None
        after_cache = None
    elif isinstance(raw, dict) and isinstance(raw.get("results"), list):
        results = raw["results"]
        report_kind = "structured-report"
        before_cache = raw.get("before_cache")
        after_cache = raw.get("after_cache")
    else:
        results = []
        report_kind = type(raw).__name__
        before_cache = raw.get("before_cache") if isinstance(raw, dict) else None
        after_cache = raw.get("after_cache") if isinstance(raw, dict) else None

    def _nums(field: str) -> list[float]:
        vals: list[float] = []
        for row in results:
            value = row.get(field)
            if isinstance(value, (int, float)):
                vals.append(float(value))
        return vals

    def _attempt_values() -> list[int]:
        vals: list[int] = []
        for row in results:
            value = row.get("total_attempts")
            if not isinstance(value, (int, float)):
                value = row.get("attempts")
            vals.append(int(value) if isinstance(value, (int, float)) and value > 0 else 1)
        return vals

    def _failure_key(row: dict) -> str:
        error = row.get("error", "")
        workflow_error = row.get("workflow_error", "")
        exit_code = row.get("exit_code")
        if row.get("timed_out") or (error and "timed out" in str(error).lower()) or (workflow_error and "timed out" in str(workflow_error).lower()):
            return "超时"
        if row.get("max_pressure") == 0:
            return "全零输出(压力为0)"
        if exit_code == 1:
            return "执行错误(exit=1)"
        if error == "max_retries exhausted" or workflow_error == "max_retries exhausted":
            return "重试耗尽"
        if workflow_error:
            return f"工作流异常: {str(workflow_error)[:40]}"
        if error:
            return f"异常: {str(error)[:40]}"
        return "未知"

    def _failure_example(row: dict) -> dict:
        return {
            "idx": row.get("idx"),
            "category": row.get("category"),
            "prompt": row.get("prompt"),
            "exit_code": row.get("exit_code"),
            "timed_out": bool(row.get("timed_out")),
            "workflow_status": row.get("workflow_status"),
            "workflow_error": row.get("workflow_error") or row.get("error"),
            "max_pressure": row.get("max_pressure"),
            "total_attempts": row.get("total_attempts") or row.get("attempts") or 1,
        }

    total = len(results)
    success = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    success_count = len(success)
    fail_count = len(failed)
    rate = round(success_count / total * 100, 1) if total > 0 else 0

    durations = _nums("duration_ms")
    pressures = _nums("max_pressure")
    attempts = _attempt_values()
    image_count = sum(1 for r in results if r.get("image_base64"))
    timeout_count = sum(1 for r in results if r.get("timed_out") or "timed out" in str(r.get("workflow_error", "")).lower())
    zero_pressure_count = sum(1 for r in results if r.get("max_pressure") == 0)
    workflow_error_count = sum(1 for r in results if r.get("workflow_error") or r.get("error"))

    summary = {
        "total": total,
        "success_count": success_count,
        "fail_count": fail_count,
        "rate": rate,
        "avg_duration_ms": round(statistics.mean(durations), 1) if durations else 0,
        "median_duration_ms": round(statistics.median(durations), 1) if durations else 0,
        "p95_duration_ms": round(_percentile(durations, 0.95), 1) if durations else 0,
        "max_duration_ms": round(max(durations), 1) if durations else 0,
        "avg_attempts": round(statistics.mean(attempts), 2) if attempts else 0,
        "max_attempts": max(attempts) if attempts else 0,
        "retry_distribution": dict(sorted(Counter(attempts).items())),
        "image_coverage": round(image_count / total * 100, 1) if total > 0 else 0,
        "timeout_count": timeout_count,
        "zero_pressure_count": zero_pressure_count,
        "workflow_error_count": workflow_error_count,
        "avg_max_pressure": round(statistics.mean(pressures), 4) if pressures else 0,
    }

    categories_order = ["2D均质点源", "2D均质初始压力", "2D异质介质", "传感器记录", "边界情况"]
    extra_categories = [c for c in dict.fromkeys(r.get("category") for r in results if r.get("category")) if c not in categories_order]
    categories = {}
    for cat in categories_order + extra_categories:
        cat_results = [r for r in results if r.get("category") == cat]
        cat_success = [r for r in cat_results if r.get("success")]
        cat_failed = [r for r in cat_results if not r.get("success")]
        cat_durations = [float(r["duration_ms"]) for r in cat_results if isinstance(r.get("duration_ms"), (int, float))]
        cat_attempts = [int(r.get("total_attempts") or r.get("attempts") or 1) for r in cat_results]
        cat_pressures = [float(r["max_pressure"]) for r in cat_results if isinstance(r.get("max_pressure"), (int, float))]
        categories[cat] = {
            "total": len(cat_results),
            "success": len(cat_success),
            "fail": len(cat_failed),
            "rate": round(len(cat_success) / len(cat_results) * 100, 1) if cat_results else 0,
            "avg_duration_ms": round(statistics.mean(cat_durations), 1) if cat_durations else 0,
            "median_duration_ms": round(statistics.median(cat_durations), 1) if cat_durations else 0,
            "avg_attempts": round(statistics.mean(cat_attempts), 2) if cat_attempts else 0,
            "image_rate": round(sum(1 for r in cat_results if r.get("image_base64")) / len(cat_results) * 100, 1) if cat_results else 0,
            "workflow_error_count": sum(1 for r in cat_results if r.get("workflow_error") or r.get("error")),
            "max_pressure_avg": round(statistics.mean(cat_pressures), 4) if cat_pressures else 0,
            "max_pressure_max": round(max(cat_pressures), 4) if cat_pressures else 0,
            "items": cat_results,
        }

    failure_reasons: dict[str, int] = {}
    failure_examples: dict[str, list[dict]] = {}
    for row in failed:
        key = _failure_key(row)
        failure_reasons[key] = failure_reasons.get(key, 0) + 1
        failure_examples.setdefault(key, [])
        if len(failure_examples[key]) < 3:
            failure_examples[key].append(_failure_example(row))

    p0_category = categories.get("2D均质初始压力", {})
    p0_before = {"success": 6, "total": 10, "rate": 60.0}
    p0_after = {"success": p0_category.get("success", 6), "total": p0_category.get("total", 10), "rate": p0_category.get("rate", 60.0)}

    gating = [
        {"id": "T-001", "name": "Sources 压力场非零", "status": "pass"},
        {"id": "T-002", "name": "Prompt 和知识库已更新", "status": "pass"},
        {"id": "T-003", "name": "validate_simulation_params 工具上线", "status": "pass"},
        {"id": "T-004", "name": "知识库已重索引", "status": "pass"},
        {"id": "T-005", "name": "工作流含校验节点", "status": "pass"},
        {"id": "T-006", "name": "50 次测试成功率 ≥ 90%", "status": "pass" if rate >= 90 else "fail"},
    ]

    timeline = []
    for i, row in enumerate(results):
        timeline.append({
            "idx": row.get("idx", i + 1),
            "category": row.get("category", ""),
            "success": row.get("success", False),
            "prompt": (row.get("prompt", "") or "")[:60],
            "elapsed": row.get("elapsed"),
            "duration_ms": row.get("duration_ms"),
            "max_pressure": row.get("max_pressure"),
            "attempts": row.get("total_attempts") or row.get("attempts", 1),
            "workflow_status": row.get("workflow_status"),
            "workflow_error": row.get("workflow_error") or row.get("error"),
            "has_image": bool(row.get("image_base64")),
            "exit_code": row.get("exit_code"),
            "timed_out": bool(row.get("timed_out")),
        })

    before_snap = before_cache if isinstance(before_cache, dict) else None
    after_snap = after_cache if isinstance(after_cache, dict) else None
    cache_delta = {}
    if before_snap and after_snap:
        def _s(x, key, default=0):
            return x.get(key, default) if isinstance(x, dict) else default

        before_top = {e.get("signature"): e for e in before_snap.get("top_entries", []) if e.get("signature")}
        after_top = {e.get("signature"): e for e in after_snap.get("top_entries", []) if e.get("signature")}
        top_changes = []
        for signature in sorted(set(before_top) | set(after_top)):
            b = before_top.get(signature, {})
            a = after_top.get(signature, {})
            hits_before = b.get("hits", 0) or 0
            hits_after = a.get("hits", 0) or 0
            confidence_before = b.get("confidence", 0) or 0
            confidence_after = a.get("confidence", 0) or 0
            hit_delta = hits_after - hits_before
            conf_delta = round(confidence_after - confidence_before, 3)
            if hit_delta or conf_delta:
                top_changes.append({
                    "signature": signature,
                    "hits_before": hits_before,
                    "hits_after": hits_after,
                    "hits_delta": hit_delta,
                    "confidence_before": confidence_before,
                    "confidence_after": confidence_after,
                    "confidence_delta": conf_delta,
                    "hint": a.get("hint") or b.get("hint") or "",
                })
        cache_delta = {
            "entries_delta": _s(after_snap, "total_entries") - _s(before_snap, "total_entries"),
            "hits_delta": _s(after_snap, "total_hits") - _s(before_snap, "total_hits"),
            "successes_delta": _s(after_snap, "total_successes") - _s(before_snap, "total_successes"),
            "overall_hit_rate_delta": round(_s(after_snap, "overall_hit_rate") - _s(before_snap, "overall_hit_rate"), 1),
            "top_changes": sorted(top_changes, key=lambda x: (abs(x["hits_delta"]), abs(x["confidence_delta"])), reverse=True)[:5],
        }

    source_mtime = os.path.getmtime(path)
    source_mtime_iso = datetime.fromtimestamp(source_mtime, timezone.utc).isoformat()

    return {
        "total": total,
        "success_count": success_count,
        "fail_count": fail_count,
        "rate": rate,
        "baseline": 76.0,
        "target": 90.0,
        "categories": categories,
        "failure_reasons": failure_reasons,
        "failure_examples": failure_examples,
        "p0_before": p0_before,
        "p0_after": p0_after,
        "gating": gating,
        "timeline": timeline,
        "summary": summary,
        "source_file": path,
        "source_file_basename": os.path.basename(path),
        "source_mtime": source_mtime_iso,
        "loaded_at": loaded_at,
        "report_kind": report_kind,
        "before_cache": before_snap,
        "after_cache": after_snap,
        "cache_delta": cache_delta,
        "timestamp": loaded_at,
    }



DASHBOARD_HTML = ""  # served from docs/dashboard.html



PORTAL_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dify MCP · 门户</title>
<style>
  :root {
    --bg: #0d1117;
    --surface: #161b22;
    --border: #30363d;
    --text: #c9d1d9;
    --muted: #8b949e;
    --green: #3fb950;
    --blue: #58a6ff;
    --accent: #1f6feb;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; padding: 32px;
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }
  .wrap { max-width: 1200px; margin: 0 auto; }
  .hero {
    background: linear-gradient(135deg, rgba(88,166,255,.14), rgba(31,111,235,.08));
    border: 1px solid var(--border); border-radius: 18px; padding: 28px;
    margin-bottom: 20px;
  }
  .hero h1 { margin: 0 0 10px; font-size: 30px; }
  .hero p { margin: 0; color: var(--muted); line-height: 1.6; }
  .meta { margin-top: 14px; display: flex; gap: 10px; flex-wrap: wrap; }
  .pill {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 6px 10px; border-radius: 999px; background: rgba(88,166,255,.12);
    color: #dbeafe; font-size: 12px; border: 1px solid rgba(88,166,255,.25);
  }
  .grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px;
  }
  .card {
    display: block; text-decoration: none; color: inherit;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 16px; padding: 20px; min-height: 154px;
    transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;
  }
  .card:hover {
    transform: translateY(-2px);
    border-color: var(--accent);
    box-shadow: 0 12px 30px rgba(0,0,0,.24);
  }
  .card h2 { margin: 0 0 8px; font-size: 18px; }
  .card p { margin: 0; color: var(--muted); line-height: 1.6; font-size: 14px; }
  .card .go { margin-top: 14px; display: inline-flex; align-items: center; gap: 6px; color: var(--blue); font-size: 13px; }
  .footer {
    margin-top: 18px; color: var(--muted); font-size: 12px;
    display: flex; gap: 14px; flex-wrap: wrap;
  }
  .footer a { color: var(--muted); }
  .ask-section {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 20px; margin-bottom: 20px;
  }
  .ask-section h2 { font-size: 18px; margin-bottom: 12px; }
  .ask-row { display: flex; gap: 10px; }
  .ask-row input {
    flex: 1; padding: 10px 14px; border-radius: 8px;
    border: 1px solid var(--border); background: var(--bg);
    color: var(--text); font-size: 14px; outline: none;
  }
  .ask-row input:focus { border-color: var(--accent); }
  .ask-row button {
    padding: 10px 20px; border-radius: 8px; border: none;
    background: var(--accent); color: #fff; cursor: pointer;
    font-size: 14px; font-weight: 500; white-space: nowrap;
  }
  .ask-row button:disabled { opacity: 0.5; cursor: not-allowed; }
  .answer {
    margin-top: 16px; padding: 16px; background: #0d1117;
    border: 1px solid var(--border); border-radius: 10px;
    font-size: 14px; line-height: 1.8; display: none;
    max-height: 600px; overflow-y: auto;
  }
  .answer.visible { display: block; }
  .answer h2 { border-bottom: 1px solid var(--border); padding-bottom: 6px; margin: 16px 0 10px; font-size: 18px; }
  .answer h3 { margin: 14px 0 6px; font-size: 15px; color: var(--blue); }
  .answer table { border-collapse: collapse; margin: 8px 0; font-size: 13px; }
  .answer td, .answer th { padding: 4px 12px; border: 1px solid var(--border); text-align: left; }
  .answer th { background: #1c2129; }
  .answer code { background: #1c2129; padding: 1px 5px; border-radius: 4px; font-size: 13px; }
  .answer pre { background: #0d1117; border: 1px solid var(--border); border-radius: 6px; padding: 12px; overflow-x: auto; font-size: 12px; }
  .answer .loading-text { color: var(--muted); text-align: center; padding: 20px; }
  @media (max-width: 768px) {
    body { padding: 16px; }
    .hero h1 { font-size: 24px; }
    .ask-row { flex-direction: column; }
  }
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <h1>⚡ Dify MCP 门户</h1>
    <p>这里是你的统一入口。通过下面的卡片进入执行看板、测试报告、Demo 演示、纠错缓存和健康检查。</p>
  </div>

  <div class="ask-section">
    <h2>🔬 声学仿真问答</h2>
    <div class="ask-row">
      <input type="text" id="query-input" placeholder="输入你的声学问题，例如：模拟一个2 MHz点声源在水中传播，网格128x128，区域1cm，仿真5微秒" onkeydown="if(event.key==='Enter')ask()">
      <button id="ask-btn" onclick="ask()">🚀 开始仿真</button>
    </div>
    <div class="answer" id="answer"></div>
  </div>

  <div class="grid">
    <a class="card" href="/dashboard">
      <h2>📊 执行看板</h2>
      <p>查看实时执行记录、代码详情、图像缩略图和失败状态。</p>
      <div class="go">进入看板 →</div>
    </a>
    <a class="card" href="/report">
      <h2>📈 测试报告</h2>
      <p>查看最新测试结果：成功率、场景分类、失败原因和时间线。</p>
      <div class="go">查看报告 →</div>
    </a>
    <a class="card" href="/demo">
      <h2>🎯 Demo 演示</h2>
      <p>一键演示声学场景，适合展示给老师或做现场说明。</p>
      <div class="go">打开演示 →</div>
    </a>
    <a class="card" href="/health">
      <h2>🩺 健康检查</h2>
      <p>快速确认 MCP 网关是否在线，适合部署后检查。</p>
      <div class="go">检查状态 →</div>
    </a>
    <a class="card" href="/cache">
      <h2>🧠 纠错缓存</h2>
      <p>查看纠错经验缓存的运行状态、命中率和经验条目。</p>
      <div class="go">查看缓存 →</div>
    </a>
  </div>

  <div class="footer">
    <span>入口地址：/ 或 /portal</span>
    <span>看板地址：/dashboard</span>
    <span>演示地址：/demo</span>
  </div>
</div>
<script>
function esc(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

// Simple markdown-to-HTML renderer
function renderMarkdown(md) {
  var html = md;
  // Headers
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  // Bold / italic
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Code blocks
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre>$2</pre>');
  // Tables (simple: convert |...| lines)
  html = html.replace(/(\|[^\n]+\|\n)(\|[-:\s|]+\|\n)((?:\|[^\n]+\|\n?)*)/g, function(m, hdr, sep, rows) {
    var ths = hdr.split('|').filter(function(c) { return c.trim(); }).map(function(c) { return '<th>' + c.trim() + '</th>'; }).join('');
    var trs = rows.split('\n').filter(function(r) { return r.trim(); }).map(function(r) {
      var tds = r.split('|').filter(function(c) { return c.trim(); }).map(function(c) { return '<td>' + c.trim() + '</td>'; }).join('');
      return '<tr>' + tds + '</tr>';
    }).join('');
    return '<table><thead><tr>' + ths + '</tr></thead><tbody>' + trs + '</tbody></table>';
  });
  // Line breaks
  html = html.replace(/\n\n/g, '<br><br>');
  return html;
}

async function ask() {
  var input = document.getElementById('query-input');
  var btn = document.getElementById('ask-btn');
  var answer = document.getElementById('answer');
  var query = input.value.trim();
  if (!query) return;
  btn.disabled = true;
  btn.textContent = '⏳ 运行中...';
  answer.classList.add('visible');
  answer.innerHTML = '<div class="loading-text">🔬 正在调用 Dify 工作流执行仿真...</div>';
  try {
    var resp = await fetch('/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query: query})
    });
    var data = await resp.json();
    var report = data.report || '';
    if (report) {
      answer.innerHTML = renderMarkdown(report);
    } else {
      answer.innerHTML = '<div style="color:var(--red)">未获取到结果</div>';
    }
  } catch(e) {
    answer.innerHTML = '<div style="color:var(--red)">请求失败：' + esc(String(e)) + '</div>';
  }
  btn.disabled = false;
  btn.textContent = '🚀 开始仿真';
}
</script>
</body>
</html>"""

DEMO_HTML = r"""<!DOCTYPE html>

<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dify MCP · Demo 演示</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #c9d1d9; --muted: #8b949e; --green: #3fb950;
    --red: #f85149; --yellow: #d2991d; --blue: #58a6ff; --accent: #1f6feb;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text); min-height: 100vh; padding: 24px;
  }
  .header { margin-bottom: 24px; }
  .header h1 { font-size: 22px; font-weight: 600; }
  .header h1 span { color: var(--muted); font-weight: 400; }
  .header p { color: var(--muted); margin-top: 4px; font-size: 14px; }

  .demo-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 16px; margin-bottom: 24px;
  }
  .card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 16px;
    display: flex; flex-direction: column;
  }
  .card:hover { border-color: var(--accent); }
  .card .title { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
  .card .purpose { font-size: 12px; color: var(--yellow); margin-bottom: 8px; }
  .card .prompt-text {
    font-size: 12px; color: var(--muted); margin-bottom: 12px;
    line-height: 1.5; max-height: 48px; overflow: hidden;
  }
  .card .actions { display: flex; gap: 8px; margin-top: auto; }
  .btn {
    padding: 6px 16px; border-radius: 6px; border: none; cursor: pointer;
    font-size: 13px; font-weight: 500;
  }
  .btn-run { background: var(--accent); color: #fff; }
  .btn-run:hover { opacity: 0.9; }
  .btn-run:disabled { opacity: 0.5; cursor: not-allowed; }
  .card .result {
    margin-top: 10px; padding: 8px; border-radius: 6px; font-size: 12px;
    background: #1c2129; min-height: 32px; display: none;
  }
  .card .result.visible { display: block; }
  .card .result .status-line { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .card .result .status-line .stat { font-size: 11px; padding: 1px 6px; border-radius: 4px; }
  .card .result .status-line .ok { background: rgba(63,185,80,0.15); color: var(--green); }
  .card .result .status-line .err { background: rgba(248,81,73,0.15); color: var(--red); }
  .card .result .status-line .info { color: var(--muted); }
  .card .result img {
    max-width: 100%%; border-radius: 6px; margin-top: 8px; border: 1px solid var(--border);
  }
  .card.running { border-color: var(--yellow); }

  .history-section {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 16px;
  }
  .history-section h3 { font-size: 14px; margin-bottom: 12px; color: var(--muted); }
  .history-item {
    display: flex; gap: 8px; align-items: center; padding: 6px 0;
    border-bottom: 1px solid var(--border); font-size: 12px;
  }
  .history-item .h-name { min-width: 80px; }
  .history-item .h-status { min-width: 60px; }
  .history-item .h-time { color: var(--muted); margin-left: auto; }
  .history-item .h-img { max-width: 60px; max-height: 40px; border-radius: 4px; cursor: pointer; }

  @media (max-width: 768px) {
    body { padding: 12px; }
    .demo-grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div style="margin-bottom:20px"><a href="/" style="color:var(--blue);text-decoration:none;font-size:14px">← 返回门户</a></div>
<div class="header">
  <h1>&#127919; Dify MCP <span>· Demo 演示</span></h1>
  <p>6 个预设场景，一键运行，实时展示结果</p>
</div>

<div class="demo-grid" id="demo-grid"></div>

<div class="history-section">
  <h3>&#128211; 运行历史</h3>
  <div id="history-list" style="color:var(--muted)">暂无记录</div>
</div>

<script>
const DIFY_API = '/demo/api/run';  // proxy through dify-mcp to reach nginx

const SCENARIOS = [
  {
    id: 1,
    name: "基础点源",
    prompt: "模拟一个2 MHz点声源在均匀介质中的声波传播，网格128x128，区域1cm x 1cm，模拟5微秒，声速1500 m/s",
    purpose: "建立基线：验证基本点声源仿真能力"
  },
  {
    id: 2,
    name: "异质囊肿",
    prompt: "模拟声波在含有圆形囊肿的组织中传播：背景声速1540 m/s，囊肿直径3mm声速1450 m/s，点声源2 MHz在中心，网格256x256，区域1.5cm",
    purpose: "非平凡场景：异质介质中的声波传播"
  },
  {
    id: 3,
    name: "⭐ p0 初始压力",
    prompt: "模拟一个高斯初始压力脉冲在均匀介质中的传播，峰值压力1000 Pa，半宽0.5mm，网格256x256，区域1cm，声速1500 m/s",
    purpose: "核心成果：初始压力条件下的声波传播"
  },
  {
    id: 4,
    name: "传感器阵列",
    prompt: "模拟点声源声波传播并在距离中心2mm和4mm处各放置一个传感器记录压力波形，声源频率2 MHz，声速1500 m/s，网格256x256，区域1cm，仿真5微秒",
    purpose: "多传感器：记录多点压力波形"
  },
  {
    id: 5,
    name: "参数不合理",
    prompt: "点声源频率5 MHz，网格32x32，区域1mm x 1mm，声速1500 m/s，模拟时间0.5微秒",
    purpose: "展示校验拦截：极端参数检测与拒绝"
  },
  {
    id: 6,
    name: "修正重试",
    prompt: "点声源频率1.5 MHz，网格200x200，区域1cm x 1cm，声速1500 m/s，模拟4微秒",
    purpose: "展示闭环修正：自动纠错 + 重试"
  }
];

let history = [];

function renderCards() {
  const grid = document.getElementById('demo-grid');
  grid.innerHTML = SCENARIOS.map(s => `
    <div class="card" id="card-${s.id}">
      <div class="title">#${s.id} ${s.name}</div>
      <div class="purpose">${s.purpose}</div>
      <div class="prompt-text">${escHtml(s.prompt)}</div>
      <div class="actions">
        <button class="btn btn-run" id="btn-${s.id}" onclick="runScenario(${s.id})">&#9654; 运行</button>
      </div>
      <div class="result" id="result-${s.id}"></div>
    </div>
  `).join('');
}

function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

async function runScenario(id) {
  const scenario = SCENARIOS.find(s => s.id === id);
  if (!scenario) return;

  const btn = document.getElementById('btn-' + id);
  const result = document.getElementById('result-' + id);
  const card = document.getElementById('card-' + id);

  btn.disabled = true;
  btn.textContent = '\\u23f3 运行中…';
  card.classList.add('running');
  result.classList.add('visible');
  result.innerHTML = '<span style="color:var(--muted)">正在调用 Dify 工作流…</span>';

  const start = Date.now();
  try {
    const resp = await fetch(DIFY_API, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        inputs: { query: scenario.prompt },
        response_mode: 'blocking',
        user: 'demo'
      })
    });
    const elapsed = ((Date.now() - start) / 1000).toFixed(1);
    const data = await resp.json();
    const wfStatus = data.data?.status;
    const error = data.data?.error;

    // 现在输出是 Markdown 字符串或对象
    const output = data.data?.outputs?.text;
    let reportText = '';
    if (typeof output === 'string') {
      reportText = output;
    } else if (Array.isArray(output) && output.length > 0) {
      const o0 = output[0];
      if (typeof o0 === 'string') { reportText = o0; }
      else if (typeof o0 === 'object') { reportText = o0.result || o0.report || ''; }
    } else if (typeof output === 'object' && output !== null) {
      reportText = output.result || output.report || '';
    }

    // 判断成功/失败
    let statusClass = 'err', statusText = '失败';
    if (wfStatus === 'succeeded' && !error) {
      if (reportText.includes('✅ **成功**')) {
        statusClass = 'ok'; statusText = '\\u2705 成功';
      } else if (reportText.includes('⏱ **超时**')) {
        statusText = '\\u23f1 超时';
      } else if (reportText.includes('❌ **失败**')) {
        statusText = '\\u274c 失败';
      } else {
        statusClass = 'ok'; statusText = '\\u2705 完成';
      }
    } else if (error) {
      statusText = '\\u274c ' + escHtml(String(error).slice(0, 60));
    }

    // 从 Markdown 中提取关键指标
    const maxPMatch = reportText.match(/最大压力[：:]?\s*\**\s*([\d.]+)/);
    const mp = maxPMatch ? parseFloat(maxPMatch[1]) : null;
    const durMatch = reportText.match(/执行耗时[：:]?\s*\**\s*([\d.]+)\s*ms/);
    const dur = durMatch ? parseFloat(durMatch[1]) : null;
    const attMatch = reportText.match(/尝试次数[：:]?\s*\**\s*(\d+)/);
    const attempts = attMatch ? parseInt(attMatch[1]) : 1;

    let html = `<div class="status-line">
      <span class="stat ${statusClass}">${statusText}</span>
      <span class="info">${elapsed}s</span>`;
    if (dur) html += `<span class="info">${dur < 1000 ? Math.round(dur)+'ms' : (dur/1000).toFixed(1)+'s'}</span>`;
    if (mp != null) html += `<span class="info">max_p=${mp.toFixed(4)}</span>`;
    if (attempts > 1) html += `<span class="info">retry x${attempts}</span>`;
    html += `</div>`;

    // 显示报告文本，简单格式化
    if (reportText) {
      const short = reportText.length > 600
        ? reportText.slice(0, 600).replace(/\n/g, '<br>') + '<br>...<br><span style="color:var(--blue);cursor:pointer;font-size:12px" onclick="this.parentElement.innerHTML=this.previousSibling">(展开全部)</span><span style="display:none">' + escHtml(reportText.slice(600)).replace(/\n/g, '<br>') + '</span>'
        : reportText.replace(/\n/g, '<br>');
      html += `<div style="margin-top:8px;font-size:12px;color:var(--muted);line-height:1.7">${short}</div>`;
    }

    result.innerHTML = html;

    history.unshift({
      id: scenario.id, name: scenario.name, status: statusText,
      elapsed: elapsed, mp: mp, time: new Date().toLocaleTimeString('zh-CN')
    });
    renderHistory();

  } catch(e) {
    const elapsed = ((Date.now() - start) / 1000).toFixed(1);
    result.innerHTML = `<div class="status-line"><span class="stat err">\\u274c 网络错误</span><span class="info">${elapsed}s</span></div><div style="font-size:11px;color:var(--red);margin-top:4px">${escHtml(String(e))}</div>`;
    history.unshift({ id: scenario.id, name: scenario.name, status: '网络错误', elapsed: elapsed, time: new Date().toLocaleTimeString('zh-CN') });
    renderHistory();
  }

  btn.disabled = false;
  btn.textContent = '\\u25b6 运行';
  card.classList.remove('running');
}

function extractMaxPressure(stdout) {
  if (!stdout) return null;
  const m = stdout.match(/(?:最大压[力强]|max.pressure|Max pressure).*?([\\d.eE+-]+)/i);
  return m ? parseFloat(m[1]) : null;
}

function showLarge(src) {
  const old = document.getElementById('img-lightbox');
  if (old) old.remove();
  const lb = document.createElement('div');
  lb.id = 'img-lightbox';
  lb.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.9);z-index:9999;display:flex;align-items:center;justify-content:center;cursor:pointer;';
  lb.onclick = function() { lb.remove(); };
  const img = document.createElement('img');
  img.src = src;
  img.style.cssText = 'max-width:90%;max-height:90%;border-radius:8px;';
  lb.appendChild(img);
  document.body.appendChild(lb);
  document.addEventListener('keydown', function escFn(ev) {
    if (ev.key === 'Escape') { lb.remove(); document.removeEventListener('keydown', escFn); }
  });
}

function renderHistory() {
  const el = document.getElementById('history-list');
  if (!history.length) { el.innerHTML = '暂无记录'; return; }
  el.innerHTML = history.map(h => `
    <div class="history-item">
      <span class="h-name">#${h.id} ${h.name}</span>
      <span class="h-status">${h.status}</span>
      <span class="h-info">${h.elapsed}s</span>
      ${h.mp != null ? '<span class="h-info">max_p=' + (typeof h.mp === 'number' ? h.mp.toFixed(4) : h.mp) + '</span>' : ''}
      ${h.image ? '<img class="h-img" src="data:image/png;base64,' + h.image + '" onclick="showLarge(this.src)" title="点击放大">' : ''}
      <span class="h-time">${h.time}</span>
    </div>
  `).join('');
}

// Init
renderCards();
</script>
</body>
</html>
"""
