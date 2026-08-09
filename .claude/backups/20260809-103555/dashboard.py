"""Execution history dashboard for Dify MCP server.

Provides SQLite-backed execution recording and a self-contained HTML
dashboard with auto-refreshing history table and test analytics.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

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


def load_test_results() -> dict:
    """Load test results and return analytics data."""
    path = _find_test_results()
    if not path:
        return {"error": "test_results_raw.json not found", "total": 0}

    with open(path, "r") as f:
        raw = json.load(f)

    if isinstance(raw, list):
        results = raw
    elif isinstance(raw, dict) and isinstance(raw.get("results"), list):
        results = raw["results"]
    else:
        results = []

    # Basic stats
    total = len(results)
    success = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]
    success_count = len(success)
    fail_count = len(failed)
    rate = round(success_count / total * 100, 1) if total > 0 else 0

    # Per-category stats
    categories_order = ["2D均质点源", "2D均质初始压力", "2D异质介质", "传感器记录", "边界情况"]
    categories = {}
    for cat in categories_order:
        cat_results = [r for r in results if r.get("category") == cat]
        cat_success = [r for r in cat_results if r.get("success")]
        categories[cat] = {
            "total": len(cat_results),
            "success": len(cat_success),
            "rate": round(len(cat_success) / len(cat_results) * 100, 1) if cat_results else 0,
            "items": cat_results,  # include full detail for expand
        }

    # Failure reasons
    failure_reasons: dict[str, int] = {}
    for r in failed:
        error = r.get("error", "")
        exit_code = r.get("exit_code")

        if r.get("timed_out") or (error and "timed out" in str(error).lower()):
            key = "超时"
        elif exit_code == 1 and r.get("max_pressure") == 0:
            key = "全零输出(压力为0)"
        elif exit_code == 1:
            key = "执行错误(exit=1)"
        elif error == "max_retries exhausted":
            key = "重试耗尽"
        elif error:
            short = str(error)[:40]
            key = f"异常: {short}"
        else:
            key = "未知"

        failure_reasons[key] = failure_reasons.get(key, 0) + 1

    # p0 fix comparison: old (before fix, results where p0 initial pressure failed)
    # In the 2026-08-08 test, p0 was 6/10 initially, then 9/10 after fix
    p0_category = categories.get("2D均质初始压力", {})
    p0_before = {"success": 6, "total": 10, "rate": 60.0}
    p0_after = {"success": p0_category.get("success", 6), "total": p0_category.get("total", 10),
                "rate": p0_category.get("rate", 60.0)}

    # Gating status (T-001 to T-006)
    gating = [
        {"id": "T-001", "name": "Sources 压力场非零", "status": "pass"},
        {"id": "T-002", "name": "Prompt 和知识库已更新", "status": "pass"},
        {"id": "T-003", "name": "validate_simulation_params 工具上线", "status": "pass"},
        {"id": "T-004", "name": "知识库已重索引", "status": "pass"},
        {"id": "T-005", "name": "工作流含校验节点", "status": "pass"},
        {"id": "T-006", "name": "50 次测试成功率 ≥ 90%", "status": "pass" if rate >= 90 else "fail"},
    ]

    # Timeline: approximate, built from test indices
    timeline = []
    for i, r in enumerate(results):
        timeline.append({
            "idx": r.get("idx", i + 1),
            "category": r.get("category", ""),
            "success": r.get("success", False),
            "prompt": (r.get("prompt", "") or "")[:60],
            "elapsed": r.get("elapsed"),
            "max_pressure": r.get("max_pressure"),
            "attempts": r.get("total_attempts", 1),
        })

    return {
        "total": total,
        "success_count": success_count,
        "fail_count": fail_count,
        "rate": rate,
        "baseline": 76.0,
        "target": 90.0,
        "categories": categories,
        "failure_reasons": failure_reasons,
        "p0_before": p0_before,
        "p0_after": p0_after,
        "gating": gating,
        "timeline": timeline,
        "source_file": path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dify MCP · 执行看板</title>
<style>
  :root {
    --bg: #0d1117;
    --surface: #161b22;
    --border: #30363d;
    --text: #c9d1d9;
    --muted: #8b949e;
    --green: #3fb950;
    --red: #f85149;
    --yellow: #d2991d;
    --blue: #58a6ff;
    --accent: #1f6feb;
    --purple: #a371f7;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 24px;
  }

  /* Tabs */
  .tab-nav {
    display: flex; gap: 4px; margin-bottom: 24px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 4px; width: fit-content;
  }
  .tab-nav button {
    padding: 8px 20px; border-radius: 7px; border: none;
    background: transparent; color: var(--muted); cursor: pointer;
    font-size: 14px; font-weight: 500; transition: all 0.15s;
  }
  .tab-nav button.active {
    background: var(--accent); color: #fff;
  }
  .tab-page { display: none; }
  .tab-page.active { display: block; }

  .header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 24px; flex-wrap: wrap; gap: 12px;
  }
  .header h1 { font-size: 22px; font-weight: 600; }
  .header h1 span { color: var(--muted); font-weight: 400; }
  .stats {
    display: flex; gap: 16px; flex-wrap: wrap;
  }
  .stat {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 16px;
    min-width: 80px;
    text-align: center;
  }
  .stat .num { font-size: 22px; font-weight: 700; }
  .stat .label { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .stat.success .num { color: var(--green); }
  .stat.fail .num { color: var(--red); }
  .stat.timeout .num { color: var(--yellow); }
  .stat.accent .num { color: var(--purple); }
  .table-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
  }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th {
    text-align: left; padding: 10px 14px;
    background: #1c2129; color: var(--muted); font-weight: 500;
    font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;
    position: sticky; top: 0; z-index: 1;
  }
  td { padding: 8px 14px; border-top: 1px solid var(--border); vertical-align: middle; }
  tr:hover { background: #1c2129; }
  .code-cell {
    max-width: 380px; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; font-family: "SF Mono", "Fira Code", monospace;
    font-size: 12px; color: var(--blue); cursor: pointer;
  }
  .code-cell:hover { color: #79c0ff; text-decoration: underline; }
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 12px;
    font-size: 12px; font-weight: 600;
  }
  .badge-ok { background: rgba(63,185,80,0.15); color: var(--green); }
  .badge-err { background: rgba(248,81,73,0.15); color: var(--red); }
  .badge-to { background: rgba(210,153,29,0.15); color: var(--yellow); }
  .time { color: var(--muted); font-size: 13px; white-space: nowrap; }
  .dur { font-size: 13px; text-align: right; }
  .empty { text-align: center; padding: 48px; color: var(--muted); }
  .empty .icon { font-size: 40px; margin-bottom: 8px; }
  .detail-row { display: none; }
  .detail-row.open { display: table-row; }
  .detail-row td { padding: 0 14px 14px 14px; border-top: none; }
  .detail-box {
    background: #0d1117; border: 1px solid var(--border); border-radius: 6px;
    padding: 12px; font-size: 12px; font-family: "SF Mono", "Fira Code", monospace;
    white-space: pre-wrap; word-break: break-all;
    max-height: 240px; overflow-y: auto;
  }
  .detail-box.code { color: var(--blue); }
  .detail-box.stdout { color: var(--text); }
  .detail-box.stderr { color: var(--red); }
  .detail-tabs { display: flex; gap: 4px; margin-bottom: 8px; }
  .detail-tab {
    padding: 4px 12px; border-radius: 4px; cursor: pointer;
    font-size: 12px; border: 1px solid var(--border); background: transparent;
    color: var(--muted);
  }
  .detail-tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  .detail-section { display: none; }
  .detail-section.active { display: block; }
  .refresh {
    font-size: 12px; color: var(--muted);
    display: flex; align-items: center; gap: 6px;
  }
  .refresh .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--green); }

  /* Analytics styles */
  .analytics-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px; margin-bottom: 20px;
  }
  .card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 16px;
  }
  .card h3 { font-size: 14px; color: var(--muted); margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
  .card h3 .icon { margin-right: 4px; }
  .progress-bar {
    height: 8px; border-radius: 4px; background: #21262d; overflow: hidden; margin-top: 6px;
  }
  .progress-fill {
    height: 100%; border-radius: 4px; transition: width 0.5s ease;
  }
  .progress-fill.green { background: var(--green); }
  .progress-fill.red { background: var(--red); }
  .progress-fill.yellow { background: var(--yellow); }
  .progress-fill.blue { background: var(--blue); }
  .progress-fill.purple { background: var(--purple); }
  .kpi-row {
    display: flex; gap: 16px; justify-content: space-between; margin-bottom: 20px;
  }
  .kpi {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 16px 20px; text-align: center; flex: 1;
  }
  .kpi .num { font-size: 32px; font-weight: 700; }
  .kpi .label { font-size: 13px; color: var(--muted); margin-top: 4px; }
  .kpi .arrow { font-size: 14px; color: var(--muted); }
  .kpi.baseline .num { color: var(--yellow); }
  .kpi.current .num { color: var(--blue); }
  .kpi.target .num { color: var(--green); }
  .cat-item {
    padding: 8px 0; cursor: pointer; border-bottom: 1px solid var(--border);
  }
  .cat-item:last-child { border-bottom: none; }
  .cat-item .label-row {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;
  }
  .cat-item .name { font-size: 13px; }
  .cat-item .count { font-size: 12px; color: var(--muted); }
  .cat-detail { display: none; margin-top: 8px; }
  .cat-detail.open { display: block; }
  .sub-item {
    padding: 4px 0 4px 16px; font-size: 12px;
    border-left: 2px solid var(--border); margin-left: 8px;
    display: flex; justify-content: space-between;
  }
  .sub-item .idx { color: var(--muted); min-width: 28px; }
  .sub-item .p { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin: 0 8px; }
  .sub-item .v { color: var(--muted); white-space: nowrap; font-family: monospace; }
  .sub-detail { display: none; }
  .sub-detail.open { display: block; }
  .gating-item {
    display: flex; align-items: center; gap: 8px; padding: 6px 0;
    font-size: 13px;
  }
  .gating-item .check { font-size: 16px; }
  .gating-item.pass .check { color: var(--green); }
  .gating-item.fail .check { color: var(--red); }
  .p0-compare {
    display: flex; gap: 16px; align-items: center; margin-top: 8px;
  }
  .p0-compare .box {
    background: #1c2129; border-radius: 8px; padding: 12px 16px; text-align: center; flex: 1;
  }
  .p0-compare .box .big { font-size: 24px; font-weight: 700; }
  .p0-compare .arrow-big { font-size: 28px; color: var(--green); }
  .p0-compare .before .big { color: var(--red); }
  .p0-compare .after .big { color: var(--green); }
  .fail-bar {
    display: flex; align-items: center; gap: 8px; margin: 4px 0;
  }
  .fail-bar .bar-bg {
    flex: 1; height: 22px; background: #21262d; border-radius: 4px; overflow: hidden; position: relative;
  }
  .fail-bar .bar-fill {
    height: 100%; border-radius: 4px; position: absolute;
  }
  .fail-bar .reason { font-size: 12px; min-width: 120px; }
  .fail-bar .count-span { font-size: 12px; color: var(--muted); min-width: 30px; text-align: right; }
  .timeline {
    max-height: 360px; overflow-y: auto;
  }
  .tl-item {
    display: flex; align-items: center; gap: 8px; padding: 3px 0; font-size: 12px;
  }
  .tl-item .tl-idx { color: var(--muted); min-width: 24px; }
  .tl-item .tl-cat { color: var(--muted); min-width: 50px; font-size: 11px; }
  .tl-item .tl-icon { min-width: 16px; text-align: center; }
  .tl-item .tl-prompt { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tl-item .tl-info { color: var(--muted); white-space: nowrap; font-family: monospace; }
  .sentence-row {
    display: flex; gap: 12px; align-items: center;
    font-size: 14px; padding: 10px 16px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; margin-bottom: 12px;
  }
  .sentence-row .label-text { color: var(--muted); }
  .sentence-row .value-text { font-weight: 700; }
  .sentence-row .value-text.good { color: var(--green); }
  .sentence-row .value-text.warn { color: var(--red); }

  @media (max-width: 768px) {
    body { padding: 12px; }
    .code-cell { max-width: 160px; }
    th:nth-child(1), td:nth-child(1) { display: none; }
    .dur { display: none; }
    .kpi-row { flex-direction: column; }
    .analytics-grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="header">
  <h1>⚡ Dify MCP <span>· 执行看板</span></h1>
</div>

<div class="tab-nav">
  <button class="active" onclick="switchPage('live')">📡 实时执行</button>
  <button onclick="switchPage('analytics'); loadAnalytics()">📊 测试分析</button>
</div>

<!-- ==================== Live Page ==================== -->
<div class="tab-page active" id="page-live">
  <div class="refresh" style="margin-bottom:12px"><span class="dot" id="live-dot"></span><span id="refresh-text">自动刷新中</span></div>
  <div class="stats" id="stats">
    <div class="stat"><div class="num" id="stat-total">-</div><div class="label">总执行</div></div>
    <div class="stat success"><div class="num" id="stat-ok">-</div><div class="label">成功</div></div>
    <div class="stat fail"><div class="num" id="stat-fail">-</div><div class="label">失败</div></div>
    <div class="stat timeout"><div class="num" id="stat-to">-</div><div class="label">超时</div></div>
  </div>
  <div class="table-wrap" style="margin-top:16px">
    <table>
      <thead><tr>
        <th>#</th><th>时间</th><th>工具</th><th>代码</th><th>图像</th><th>状态</th><th class="dur">耗时</th>
      </tr></thead>
      <tbody id="rows"><tr><td colspan="7" class="empty"><div class="icon">📭</div>等待 Dify 发送第一条代码…</td></tr></tbody>
    </table>
  </div>
</div>

<!-- ==================== Analytics Page ==================== -->
<div class="tab-page" id="page-analytics">
  <div class="refresh" style="margin-bottom:12px"><span id="analytics-ts">加载中…</span></div>

  <!-- Gate status -->
  <div class="card" style="margin-bottom:20px">
    <h3>🚦 阶段一门禁进度</h3>
    <div id="gating-list">加载中…</div>
  </div>

  <!-- 3 KPIs -->
  <div class="kpi-row">
    <div class="kpi baseline"><div class="num" id="kpi-baseline">76%</div><div class="label">基线成功率</div></div>
    <div class="kpi current"><div class="num" id="kpi-current">-</div><div class="label">当前成功率</div></div>
    <div class="kpi target"><div class="num" id="kpi-target">90%</div><div class="label">门禁目标</div></div>
  </div>

  <div class="analytics-grid">
    <!-- Category breakdown -->
    <div class="card">
      <h3>📂 各场景成功率</h3>
      <div id="cat-list">加载中…</div>
    </div>

    <!-- Failure reasons -->
    <div class="card">
      <h3>🔍 失败原因分布</h3>
      <div id="fail-chart">加载中…</div>
    </div>

    <!-- p0 fix comparison -->
    <div class="card">
      <h3>⭐ p0 初始压力修复对比</h3>
      <div id="p0-compare">加载中…</div>
    </div>

    <!-- Timeline -->
    <div class="card">
      <h3>📜 修复历程时间线</h3>
      <div class="timeline" id="timeline">加载中…</div>
    </div>
  </div>

  <!-- Cache stats -->
  <div class="card" style="margin-top:16px">
    <h3>🧠 纠错经验缓存</h3>
    <div id="cache-stats">加载中…</div>
  </div>
</div>

<script>
// ===== Tab switching =====
function switchPage(name) {
  document.querySelectorAll('.tab-page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  document.querySelectorAll('.tab-nav button').forEach(b => b.classList.remove('active'));
  if (name === 'live') {
    document.querySelector('.tab-nav button:nth-child(1)').classList.add('active');
  } else {
    document.querySelector('.tab-nav button:nth-child(2)').classList.add('active');
  }
}

// ===== Live page =====
let lastId = 0;
let firstLoad = true;

function timeAgo(ts) {
  const d = new Date(ts), now = new Date();
  const s = Math.floor((now - d) / 1000);
  let relative;
  if (s < 60) relative = s + "秒前";
  else if (s < 3600) relative = Math.floor(s/60) + "分钟前";
  else relative = Math.floor(s/3600) + "小时前";
  const dateStr = d.toLocaleString("zh-CN", {
    month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit"
  });
  return relative + " (" + dateStr + ")";
}

function esc(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function trunc(s, n) {
  s = String(s).replace(/\\n/g," ").replace(/\\s+/g," ").trim();
  return s.length > n ? s.slice(0,n) + "…" : s;
}

function badge(exit, to) {
  if (to) return '<span class="badge badge-to">超时</span>';
  if (exit === 0) return '<span class="badge badge-ok">成功</span>';
  return '<span class="badge badge-err">失败 (' + exit + ')</span>';
}

function renderRow(r) {
  const dur = r.duration_ms != null ? (r.duration_ms < 1000 ? r.duration_ms+"ms" : (r.duration_ms/1000).toFixed(1)+"s") : "-";
  const hasImg = r.image_base64 && r.image_base64.length > 100;
  const imgCell = hasImg
    ? `<td class="img-cell" style="text-align:center" onclick="event.stopPropagation()">
         <img class="gallery-thumb" src="data:image/png;base64,${r.image_base64}" style="max-width:48px;max-height:48px;border-radius:4px;border:1px solid var(--border);cursor:pointer" title="点击查看大图" onclick="event.stopPropagation();showLightbox(this.src)">
       </td>`
    : `<td class="img-cell" style="text-align:center;color:var(--muted)">-</td>`;
  return `<tr onclick="toggleDetail(${r.id})" style="cursor:pointer">
    <td style="color:var(--muted);font-size:12px">${r.id}</td>
    <td class="time" title="${r.timestamp}">${timeAgo(r.timestamp)}</td>
    <td style="font-size:13px">${esc(r.tool_name)}</td>
    <td class="code-cell">${esc(trunc(r.code,60))}</td>
    ${imgCell}
    <td>${badge(r.exit_code, r.timed_out)}</td>
    <td class="dur">${dur}</td>
  </tr>
  <tr class="detail-row" id="detail-${r.id}">
    <td colspan="7">
      <div class="detail-tabs">
        <span class="detail-tab active" onclick="event.stopPropagation();switchTab(${r.id},'code')">📝 代码</span>
        <span class="detail-tab" onclick="event.stopPropagation();switchTab(${r.id},'stdout')">📤 stdout</span>
        <span class="detail-tab" onclick="event.stopPropagation();switchTab(${r.id},'stderr')">📥 stderr</span>
      </div>
      <div class="detail-section active" id="sec-${r.id}-code"><div class="detail-box code">${esc(r.code)}</div></div>
      <div class="detail-section" id="sec-${r.id}-stdout"><div class="detail-box stdout">${esc(r.stdout) || "(无输出)"}</div></div>
      <div class="detail-section" id="sec-${r.id}-stderr"><div class="detail-box stderr">${esc(r.stderr) || "(无输出)"}</div></div>
    </td>
  </tr>`;
}

function toggleDetail(id) {
  const row = document.getElementById("detail-" + id);
  row.classList.toggle("open");
}

function switchTab(id, tab) {
  ["code","stdout","stderr"].forEach(t => {
    document.getElementById("sec-"+id+"-"+t).classList.toggle("active", t===tab);
  });
  const tabs = document.querySelectorAll("#detail-"+id+" .detail-tab");
  tabs.forEach((el,i) => el.classList.toggle("active", ["code","stdout","stderr"][i]===tab));
}

async function refresh() {
  try {
    const resp = await fetch("/dashboard/api/executions?since=" + lastId + "&limit=100");
    const data = await resp.json();
    if (data.executions && data.executions.length > 0) {
      const rows = document.getElementById("rows");
      if (firstLoad) { rows.innerHTML = ""; firstLoad = false; }
      // 最新在前；接口返回本身就是倒序，这里反向插入，保证页面从上到下也是最新→最旧
      data.executions.slice().reverse().forEach(r => {
        if (document.getElementById("detail-"+r.id)) return;
        rows.insertAdjacentHTML("afterbegin", renderRow(r));
        lastId = Math.max(lastId, r.id);
      });
    }
    if (data.stats) {
      document.getElementById("stat-total").textContent = data.stats.total;
      document.getElementById("stat-ok").textContent = data.stats.success;
      document.getElementById("stat-fail").textContent = data.stats.failed;
      document.getElementById("stat-to").textContent = data.stats.timeout;
    }
    document.getElementById("live-dot").style.background = "var(--green)";
    document.getElementById("refresh-text").textContent = "自动刷新中";
  } catch(e) {
    document.getElementById("live-dot").style.background = "var(--red)";
    document.getElementById("refresh-text").textContent = "连接断开";
  }
}

// ===== Analytics page =====
async function loadAnalytics() {
  try {
    const resp = await fetch("/dashboard/api/test_report");
    const d = await resp.json();
    renderAnalytics(d);
  } catch(e) {
    document.getElementById("gating-list").textContent = "加载失败: " + e;
  }
  // Also load cache stats
  try {
    const cr = await fetch("/dashboard/api/cache_stats");
    const cd = await cr.json();
    renderCacheStats(cd);
  } catch(e) {}
}

const CAT_COLORS = ["#58a6ff","#a371f7","#3fb950","#d2991d","#f85149"];

function renderAnalytics(d) {
  // Timestamp
  document.getElementById("analytics-ts").innerHTML =
    '<span class="dot" style="background:var(--green);display:inline-block;width:6px;height:6px;border-radius:50%"></span> 数据时间: ' + (d.timestamp || '未知') +
    (d.source_file ? ' · 来源: ' + esc(String(d.source_file).split('/').pop()) : '');

  // Gate
  let gatingHtml = '';
  d.gating.forEach(g => {
    const cls = g.status === 'pass' ? 'pass' : 'fail';
    const icon = g.status === 'pass' ? '✅' : '❌';
    gatingHtml += `<div class="gating-item ${cls}"><span class="check">${icon}</span> ${g.id} · ${esc(g.name)}</div>`;
  });
  document.getElementById("gating-list").innerHTML = gatingHtml;

  // KPIs
  document.getElementById("kpi-baseline").textContent = d.baseline + '%';
  document.getElementById("kpi-current").textContent = d.rate + '%';
  document.getElementById("kpi-target").textContent = d.target + '%';
  // Color the current KPI
  const kpiEl = document.getElementById("kpi-current");
  if (d.rate >= 90) kpiEl.style.color = 'var(--green)';
  else if (d.rate >= 80) kpiEl.style.color = 'var(--yellow)';
  else kpiEl.style.color = 'var(--red)';

  // Categories
  let catHtml = '';
  const catKeys = Object.keys(d.categories);
  catKeys.forEach((cat, i) => {
    const c = d.categories[cat];
    const color = CAT_COLORS[i % CAT_COLORS.length];
    catHtml += `<div class="cat-item" onclick="toggleCatDetail('cat-${i}')">
      <div class="label-row">
        <span class="name">${esc(cat)}</span>
        <span class="count">${c.success}/${c.total} (${c.rate}%)</span>
      </div>
      <div class="progress-bar"><div class="progress-fill" style="width:${c.rate}%;background:${color}"></div></div>
      <div class="cat-detail" id="cat-${i}">`;
    (c.items || []).forEach(it => {
      const icon = it.success ? '✅' : '❌';
      const mp = it.max_pressure != null ? 'p=' + (typeof it.max_pressure === 'number' ? it.max_pressure.toFixed(4) : it.max_pressure) : '';
      const att = it.total_attempts ? '×' + it.total_attempts : '';
      const dur = it.duration_ms ? (it.duration_ms < 1000 ? it.duration_ms + 'ms' : (it.duration_ms/1000).toFixed(1)+'s') : '';
      const detailId = 'sub-' + it.idx;
      catHtml += `<div class="sub-item" onclick="event.stopPropagation();toggleSubDetail('${detailId}')">
        <span class="idx">#${it.idx}</span>
        <span class="p">${esc((it.prompt||'').slice(0,50))}</span>
        <span class="v">${icon} ${mp} ${att} ${dur}</span>
      </div>
      <div class="sub-detail" id="${detailId}">
        <div class="detail-box code" style="margin-left:28px;margin-bottom:4px;">Prompt: ${esc(it.prompt||'')}</div>
        <div class="detail-box stdout" style="margin-left:28px;">stdout: ${esc(it.stdout||'(无)')}</div>
      </div>`;
    });
    catHtml += '</div></div>';
  });
  document.getElementById("cat-list").innerHTML = catHtml;

  // Failure reasons -- horizontal bar chart
  let failHtml = '';
  const reasons = Object.entries(d.failure_reasons || {}).sort((a,b) => b[1]-a[1]);
  const maxCount = reasons.length > 0 ? Math.max(...reasons.map(r=>r[1])) : 1;
  const failColors = ['#f85149','#d2991d','#c9d1d9','#8b949e','#484f58'];
  reasons.forEach((r, i) => {
    const pct = Math.round(r[1] / d.fail_count * 100);
    const color = failColors[i % failColors.length];
    failHtml += `<div class="fail-bar">
      <span class="reason">${esc(r[0])}</span>
      <div class="bar-bg"><div class="bar-fill" style="width:${pct}%;background:${color}"></div></div>
      <span class="count-span">${r[1]}次 (${pct}%)</span>
    </div>`;
  });
  if (!reasons.length) failHtml = '<div style="color:var(--green);text-align:center;padding:16px">🎉 没有失败！</div>';
  document.getElementById("fail-chart").innerHTML = failHtml;

  // p0 compare
  const pb = d.p0_before || {success:6,total:10,rate:60};
  const pa = d.p0_after || {success:9,total:10,rate:90};
  const improve = pa.success - pb.success;
  document.getElementById("p0-compare").innerHTML = `
    <div class="p0-compare">
      <div class="box before"><div class="big">${pb.success}/${pb.total}</div><div style="color:var(--muted);font-size:12px">修复前</div><div style="font-size:12px;color:var(--red)">${pb.rate}%</div></div>
      <div class="arrow-big">→</div>
      <div class="box after"><div class="big">${pa.success}/${pa.total}</div><div style="color:var(--muted);font-size:12px">修复后</div><div style="font-size:12px;color:var(--green)">${pa.rate}%</div></div>
    </div>
    <div style="text-align:center;margin-top:8px;font-size:13px;color:var(--green)">+${improve} 次成功，提升 +${(pa.rate-pb.rate).toFixed(0)}%</div>`;

  // Timeline
  let tlHtml = '';
  d.timeline.forEach(t => {
    const icon = t.success ? '✅' : '❌';
    const mp = t.max_pressure != null ? 'p=' + (typeof t.max_pressure === 'number' ? t.max_pressure.toFixed(2) : t.max_pressure) : '';
    tlHtml += `<div class="tl-item">
      <span class="tl-idx">#${t.idx}</span>
      <span class="tl-cat">${esc(t.category||'')}</span>
      <span class="tl-icon">${icon}</span>
      <span class="tl-prompt" title="${esc(t.prompt||'')}">${esc((t.prompt||'').slice(0,40))}</span>
      <span class="tl-info">${mp} ${t.attempts>1?'×'+t.attempts:''}</span>
    </div>`;
  });
  document.getElementById("timeline").innerHTML = tlHtml;
}

function renderCacheStats(d) {
  const el = document.getElementById("cache-stats");
  if (d.total_entries === 0) {
    el.innerHTML = '<div style="color:var(--muted);text-align:center;padding:16px">暂无缓存经验。运行带有 retry 的仿真后，LLM 修复经验将自动沉淀到这里。</div>';
    return;
  }
  let html = `<div style="display:flex;gap:24px;margin-bottom:12px;flex-wrap:wrap">
    <div style="text-align:center"><span style="font-size:28px;font-weight:700;color:var(--blue)">${d.total_entries}</span><div style="font-size:12px;color:var(--muted)">总经验条目</div></div>
    <div style="text-align:center"><span style="font-size:28px;font-weight:700;color:var(--green)">${d.total_hits}</span><div style="font-size:12px;color:var(--muted)">累计命中次数</div></div>
    <div style="text-align:center"><span style="font-size:28px;font-weight:700;color:var(--purple)">${d.overall_hit_rate}%</span><div style="font-size:12px;color:var(--muted)">整体成功率</div></div>
  </div>`;
  if (d.top_entries && d.top_entries.length > 0) {
    html += '<div style="font-size:13px;color:var(--muted);margin-bottom:6px">Top 高频经验：</div>';
    d.top_entries.forEach((e, i) => {
      html += `<div style="padding:6px 10px;margin:4px 0;background:#1c2129;border-radius:6px;font-size:12px">
        <span style="color:var(--muted)">#${i+1}</span>
        <span style="font-family:monospace;color:var(--yellow);margin:0 8px">${esc(e.signature)}</span>
        <span style="color:var(--green)">${e.hits}次命中</span>
        <span style="color:var(--muted);margin-left:4px">置信度 ${(e.confidence*100).toFixed(0)}%</span>
        <div style="color:var(--muted);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(e.hint.substring(0, 120))}</div>
      </div>`;
    });
  }
  el.innerHTML = html;
}

function toggleCatDetail(id) {
  document.getElementById(id).classList.toggle('open');
}

function toggleSubDetail(id) {
  document.getElementById(id).classList.toggle('open');
}

// ===== Image Gallery =====
function showImageModal(id) {
  const row = rowsEl && rowsEl.querySelector ? rowsEl : document.getElementById("rows");
  let img = null;
  // Try to find from stored data
  if (window._galleryImages && window._galleryImages[id]) {
    img = window._galleryImages[id];
  }
  if (!img) {
    // fallback: try to read from DOM
    const codeCell = document.querySelector(`#detail-${id} .detail-box.code`);
    // not used this way, use data attribute
  }
  return;
}

// Store gallery images on row render
(function() {
  const origRender = renderRow;
  window._galleryImages = window._galleryImages || {};
  renderRow = function(r) {
    if (r.image_base64 && r.image_base64.length > 100) {
      window._galleryImages[r.id] = r.image_base64;
    }
    return origRender(r);
  };
})();

// Listen for clicks on thumbnail images
document.addEventListener('click', function(e) {
  const img = e.target.closest('.gallery-thumb');
  if (!img) return;
  e.stopPropagation();
  const src = img.src;
  showLightbox(src);
});

function showLightbox(src) {
  // Remove existing
  const old = document.getElementById('gallery-lightbox');
  if (old) old.remove();
  const lb = document.createElement('div');
  lb.id = 'gallery-lightbox';
  lb.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.9);z-index:9999;display:flex;align-items:center;justify-content:center;cursor:pointer;';
  lb.onclick = function() { lb.remove(); };
  const inner = document.createElement('img');
  inner.src = src;
  inner.style.cssText = 'max-width:90%;max-height:90%;border-radius:8px;box-shadow:0 0 40px rgba(0,0,0,0.5);';
  lb.appendChild(inner);
  document.body.appendChild(lb);
  // Close on Escape
  document.addEventListener('keydown', function escFn(ev) {
    if (ev.key === 'Escape') { lb.remove(); document.removeEventListener('keydown', escFn); }
  });
}

// Initial load
refresh();
setInterval(refresh, 3000);

let rowsEl = document.getElementById("rows");

// Check for hash-based tab
if (window.location.hash === '#analytics') { switchPage('analytics'); loadAnalytics(); }
</script>
</body>
</html>"""


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
  @media (max-width: 768px) {
    body { padding: 16px; }
    .hero h1 { font-size: 24px; }
  }
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <h1>⚡ Dify MCP 门户</h1>
    <p>这里是你的统一入口。通过下面的卡片进入看板、测试分析、演示页和健康检查。</p>
    <div class="meta">
      <span class="pill">门户入口</span>
      <span class="pill">执行看板</span>
      <span class="pill">测试分析</span>
      <span class="pill">Demo 演示</span>
      <span class="pill">健康检查</span>
    </div>
  </div>

  <div class="grid">
    <a class="card" href="/dashboard">
      <h2>📊 执行看板</h2>
      <p>查看实时执行记录、代码详情、图像缩略图和失败状态。</p>
      <div class="go">进入看板 →</div>
    </a>
    <a class="card" href="/dashboard#analytics">
      <h2>📈 测试分析</h2>
      <p>查看 T-006 成功率、场景分类、失败原因和纠错缓存统计。</p>
      <div class="go">查看分析 →</div>
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
    <a class="card" href="/dashboard/api/test_report">
      <h2>🧾 测试报告 API</h2>
      <p>直接查看最新测试报告数据，方便排查看板同步问题。</p>
      <div class="go">查看 API →</div>
    </a>
    <a class="card" href="/dashboard/api/cache_stats">
      <h2>🧠 纠错缓存 API</h2>
      <p>查看缓存命中、成功率和高频经验条目。</p>
      <div class="go">查看缓存 →</div>
    </a>
  </div>

  <div class="footer">
    <span>入口地址：/ 或 /portal</span>
    <span>看板地址：/dashboard</span>
    <span>演示地址：/demo</span>
  </div>
</div>
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
    const outputs = data.data?.outputs?.text || [];
    let o = outputs.length ? (Array.isArray(outputs) ? outputs[0] : outputs) : {};

    let statusClass = 'err', statusText = '失败';
    let mp = null, attempts = 1, dur = null;

    if (wfStatus === 'succeeded' && !error) {
      if (o.exit_code === 0 && !o.timed_out) {
        statusClass = 'ok';
        statusText = '\\u2705 成功';
      } else if (o.timed_out) {
        statusText = '\\u23f1 超时';
      } else {
        statusText = '\\u274c 错误 (exit=' + o.exit_code + ')';
      }
      mp = o.max_pressure != null ? o.max_pressure : extractMaxPressure(o.stdout);
      attempts = o.total_attempts || 1;
      dur = o.duration_ms;
    }

    let html = `<div class="status-line">
      <span class="stat ${statusClass}">${statusText}</span>
      <span class="info">${elapsed}s</span>`;
    if (dur) html += `<span class="info">${dur < 1000 ? Math.round(dur)+'ms' : (dur/1000).toFixed(1)+'s'}</span>`;
    if (mp != null) html += `<span class="info">max_p=${typeof mp === 'number' ? mp.toFixed(4) : mp}</span>`;
    if (attempts > 1) html += `<span class="info">retry x${attempts}</span>`;
    html += `</div>`;

    if (o.image_base64 && o.image_base64.length > 100) {
      html += `<img src="data:image/png;base64,${o.image_base64}" onclick="showLarge(this.src)" title="点击放大">`;
    }

    result.innerHTML = html;

    history.unshift({
      id: scenario.id, name: scenario.name, status: statusText,
      elapsed: elapsed, mp: mp, image: o.image_base64, time: new Date().toLocaleTimeString('zh-CN')
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
