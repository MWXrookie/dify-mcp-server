"""Execution history dashboard for Dify MCP server.

Provides SQLite-backed execution recording and a self-contained HTML
dashboard with auto-refreshing history table.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

DB_PATH = "/app/data/execution_history.db"
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
            attempt_count INTEGER DEFAULT 1
        )
    """)
    # 为旧表补充可能缺失的列（向前兼容）
    try:
        db.execute("ALTER TABLE executions ADD COLUMN attempt_count INTEGER DEFAULT 1")
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
) -> None:
    with _write_lock:
        db = _get_db()
        db.execute(
            "INSERT INTO executions (timestamp, tool_name, code, exit_code, timed_out, duration_ms, stdout, stderr, attempt_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
    result = [dict(r) for r in reversed(rows)]
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
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 24px;
  }
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
  @media (max-width: 768px) {
    body { padding: 12px; }
    .code-cell { max-width: 160px; }
    th:nth-child(1), td:nth-child(1) { display: none; }
    .dur { display: none; }
  }
</style>
</head>
<body>
<div class="header">
  <h1>⚡ Dify MCP <span>· 执行看板</span></h1>
  <div class="refresh"><span class="dot" id="live-dot"></span><span id="refresh-text">自动刷新中</span></div>
</div>
<div class="stats" id="stats">
  <div class="stat"><div class="num" id="stat-total">-</div><div class="label">总执行</div></div>
  <div class="stat success"><div class="num" id="stat-ok">-</div><div class="label">成功</div></div>
  <div class="stat fail"><div class="num" id="stat-fail">-</div><div class="label">失败</div></div>
  <div class="stat timeout"><div class="num" id="stat-to">-</div><div class="label">超时</div></div>
</div>
<div class="table-wrap" style="margin-top:16px">
  <table>
    <thead><tr>
      <th>#</th><th>时间</th><th>工具</th><th>代码</th><th>状态</th><th class="dur">耗时</th>
    </tr></thead>
    <tbody id="rows"><tr><td colspan="6" class="empty"><div class="icon">📭</div>等待 Dify 发送第一条代码…</td></tr></tbody>
  </table>
</div>

<script>
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
  return `<tr onclick="toggleDetail(${r.id})" style="cursor:pointer">
    <td style="color:var(--muted);font-size:12px">${r.id}</td>
    <td class="time" title="${r.timestamp}">${timeAgo(r.timestamp)}</td>
    <td style="font-size:13px">${esc(r.tool_name)}</td>
    <td class="code-cell">${esc(trunc(r.code,60))}</td>
    <td>${badge(r.exit_code, r.timed_out)}</td>
    <td class="dur">${dur}</td>
  </tr>
  <tr class="detail-row" id="detail-${r.id}">
    <td colspan="6">
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
      data.executions.forEach(r => {
        // 避免重复行
        if (document.getElementById("detail-"+r.id)) return;
        rows.insertAdjacentHTML("beforeend", renderRow(r));
        lastId = Math.max(lastId, r.id);
      });
      // 滚动到最新
      const wrap = document.querySelector(".table-wrap");
      if (wrap.scrollTop + wrap.clientHeight >= wrap.scrollHeight - 200) {
        wrap.scrollTop = wrap.scrollHeight;
      }
    }
    // 更新统计
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

refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>"""
